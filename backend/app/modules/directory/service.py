"""Who is responsible for what, where: localities, their committee, and the bodies serving them."""

import uuid
from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuthorityType, Channel, ContactSource
from app.db.models import (
    Authority,
    AuthorityArea,
    AuthorityContact,
    Locality,
    Municipality,
    PlanningCommittee,
    Project,
    Requirement,
    Thread,
)
from app.modules.directory.schemas import AuthorityOut, ContactOut, LocalityOut

# Bodies outside the project team whose addresses are worth remembering.
LEARNABLE = {
    AuthorityType.municipality,
    AuthorityType.water_corporation,
    AuthorityType.fire_department,
    AuthorityType.home_front_command,
    AuthorityType.testing_lab,
    AuthorityType.green_building_lab,
    AuthorityType.electrical_inspector,
    AuthorityType.surveyor,
}


def _locality_query():  # type: ignore[no-untyped-def]
    return (
        select(Locality, Municipality, PlanningCommittee)
        .outerjoin(Municipality, Municipality.code == Locality.municipality_code)
        .outerjoin(PlanningCommittee, PlanningCommittee.code == Municipality.committee_code)
    )


def _locality_out(
    loc: Locality, m: Municipality | None, c: PlanningCommittee | None
) -> LocalityOut:
    return LocalityOut(
        code=loc.code,
        name=loc.name,
        municipality_code=m.code if m else None,
        municipality=m.name if m else None,
        committee_code=c.code if c else None,
        committee=c.name if c else None,
        committee_source=m.committee_source if m else None,
    )


async def search_localities(db: AsyncSession, query: str, limit: int = 12) -> list[LocalityOut]:
    q = query.strip()
    if not q:
        return []
    rows = await db.execute(
        _locality_query()
        .where(or_(Locality.name.ilike(f"%{q}%"), Locality.name_en.ilike(f"%{q}%")))
        # Exact, then prefix, then contains; shorter names first ("רעננה" before "רעננה צפון").
        .order_by(
            case((Locality.name == q, 0), (Locality.name.ilike(f"{q}%"), 1), else_=2),
            func.length(Locality.name),
        )
        .limit(limit)
    )
    return [_locality_out(*row) for row in rows]


async def get_locality(db: AsyncSession, code: int) -> LocalityOut | None:
    row = (await db.execute(_locality_query().where(Locality.code == code))).first()
    return _locality_out(*row) if row else None


async def authorities_for(db: AsyncSession, municipality_code: int) -> list[AuthorityOut]:
    """Bodies serving a municipality, plus national ones, with their contacts."""
    area_ids = select(AuthorityArea.authority_id).where(
        AuthorityArea.municipality_code == municipality_code
    )
    authorities = list(
        await db.scalars(
            select(Authority)
            .where(or_(Authority.id.in_(area_ids), Authority.national.is_(True)))
            .order_by(Authority.type, Authority.name)
        )
    )
    contacts: dict[uuid.UUID, list[ContactOut]] = {}
    for c in await db.scalars(
        select(AuthorityContact)
        .where(AuthorityContact.authority_id.in_([a.id for a in authorities]))
        .order_by(AuthorityContact.source, AuthorityContact.purpose)
    ):
        contacts.setdefault(c.authority_id, []).append(
            ContactOut(
                id=c.id,
                purpose=c.purpose,
                channel=c.channel,
                email=c.email,
                phone=c.phone,
                url=c.url,
                source=c.source,
                source_url=c.source_url,
                verified_at=c.verified_at,
            )
        )
    return [
        AuthorityOut(
            id=a.id,
            type=a.type,
            name=a.name,
            website=a.website,
            permit_search_url=a.permit_search_url,
            national=a.national,
            contacts=contacts.get(a.id, []),
        )
        for a in authorities
    ]


async def learn_from_thread(
    db: AsyncSession, project: Project, thread: Thread, requirement_id: uuid.UUID | None
) -> AuthorityContact | None:
    """When a conversation is filed under a requirement, remember the sender as a contact of the
    body responsible for that requirement in this area. The directory grows with every project."""
    if requirement_id is None or project.municipality_code is None:
        return None
    requirement = await db.get(Requirement, requirement_id)
    if requirement is None or requirement.authority_type not in LEARNABLE:
        return None
    email = thread.counterparty_email.lower()
    area_ids = select(AuthorityArea.authority_id).where(
        AuthorityArea.municipality_code == project.municipality_code
    )
    authority = await db.scalar(
        select(Authority).where(
            Authority.type == requirement.authority_type,
            or_(Authority.id.in_(area_ids), Authority.national.is_(True)),
        )
    )
    if authority is None:
        # First time anyone in this area heard from such a body: start its entry.
        authority = Authority(
            type=requirement.authority_type,
            name=thread.counterparty_name or email.split("@")[-1],
        )
        db.add(authority)
        await db.flush()
        db.add(
            AuthorityArea(authority_id=authority.id, municipality_code=project.municipality_code)
        )
    exists = await db.scalar(
        select(AuthorityContact.id).where(
            AuthorityContact.authority_id == authority.id,
            func.lower(AuthorityContact.email) == email,
        )
    )
    if exists:
        return None
    contact = AuthorityContact(
        authority_id=authority.id,
        purpose=requirement.title[:100],
        channel=Channel.email,
        email=email,
        source=ContactSource.learned,
        verified_at=date.today(),
        project_id=project.id,
    )
    db.add(contact)
    return contact
