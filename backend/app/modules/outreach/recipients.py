"""Who to write to about a requirement, and how they take requests."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuthorityType, Channel, ContactSource
from app.db.models import Project, Requirement, Thread
from app.modules.directory.service import authorities_for

# The approving bodies Arba writes to. Professionals (surveyor, lab, engineers) come later,
# with their own upload links.
WRITES_TO = {
    AuthorityType.municipality,
    AuthorityType.water_corporation,
    AuthorityType.fire_department,
    AuthorityType.home_front_command,
}


@dataclass
class Recipient:
    channel: Channel
    name: str | None = None
    email: str | None = None
    portal_url: str | None = None
    phone: str | None = None
    authority_id: object | None = None
    # thread (the conversation already under way), official_site, learned, user, none.
    source: str = "none"


async def find_recipient(db: AsyncSession, project: Project, requirement: Requirement) -> Recipient:
    # 1. The conversation about this step is already under way: answer there.
    thread = await db.scalar(
        select(Thread)
        .where(Thread.project_id == project.id, Thread.requirement_id == requirement.id)
        .order_by(Thread.last_message_at.desc())
        .limit(1)
    )
    if thread and thread.counterparty_email:
        return Recipient(
            channel=Channel.email,
            name=thread.counterparty_name,
            email=thread.counterparty_email,
            source="thread",
        )

    # 2. The directory: the body of this type that serves the project's area.
    authorities = (
        await authorities_for(db, project.municipality_code) if project.municipality_code else []
    )
    candidates = [a for a in authorities if a.type == requirement.authority_type]
    # Local bodies before national ones.
    candidates.sort(key=lambda a: a.national)
    for authority in candidates:
        # Learned addresses are the ones that actually answered; then the official ones.
        contacts = sorted(
            authority.contacts,
            key=lambda c: (
                c.source != ContactSource.learned,
                c.source != ContactSource.official_site,
            ),
        )
        email = next((c for c in contacts if c.channel == Channel.email and c.email), None)
        if email:
            return Recipient(
                channel=Channel.email,
                name=authority.name,
                email=email.email,
                phone=email.phone,
                authority_id=authority.id,
                source=email.source.value,
            )
        portal = next((c for c in contacts if c.channel == Channel.portal and c.url), None)
        visit = next((c for c in contacts if c.channel == Channel.in_person), None)
        url = (portal.url if portal else None) or authority.website
        if url or visit:
            return Recipient(
                channel=Channel.portal if url else Channel.in_person,
                name=authority.name,
                portal_url=url or (visit.url if visit else None),
                phone=next((c.phone for c in contacts if c.phone), None),
                authority_id=authority.id,
                source=next((c.source.value for c in (portal, visit) if c), "official_site"),
            )
    # 3. Not known yet: the person fills in the address (and Arba learns it from the reply).
    return Recipient(channel=Channel.email, name=candidates[0].name if candidates else None)
