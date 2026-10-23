"""Resets the demo account to a rich, consistent project for showing Arba to customers.

    python -m app.scripts.demo [--password PASSWORD] [--remove-email EMAIL ...]

Deletes the demo user's projects (and the projects and accounts of any --remove-email), then
builds "the Levi family's house" in Raanana, halfway through the frame: permit verified, its
conditions read, early stages done with real documents, a team of professionals, a request
answered through an upload link, a document Arba flagged, mail waiting for approval and a
letter to the water corporation. Everything goes through Arba's own services, so the data is
what the app itself would produce. Safe to run again before every demo.

Point it at the target database with ARBA_DATABASE_URL and run it with
ARBA_STORAGE_BACKEND=database for a serverless deployment.
"""

import argparse
import asyncio
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AuthorityType,
    ConditionTiming,
    DocumentSource,
    DocumentStatus,
    RequestStatus,
)
from app.core.enums import RequirementStatus as S
from app.core.security import hash_password
from app.core.storage import get_storage
from app.db.models import (
    AuditLog,
    Document,
    DocumentRequest,
    Membership,
    Organization,
    PermitCondition,
    Project,
    ProjectMember,
    Requirement,
    TemplateRequirement,
    User,
)
from app.db.session import SessionLocal, engine
from app.email.parsing import parse_rfc822
from app.email.processing import document_key, store_email
from app.modules.catchup.service import catch_up
from app.modules.checks.service import check_pending
from app.modules.outreach.service import create_draft
from app.modules.permits import conditions_service
from app.modules.permits.service import confirm_with_committee, run_checks
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import create_project
from app.modules.requirements.service import change_status
from app.modules.suggestions.service import RulesClassifier, suggest_for_message
from app.modules.team.schemas import ContactIn, RequestCreate
from app.modules.team.service import add_contact, create_request

DEMO_EMAIL = "demo@example.com"
FILES = Path(__file__).parent / "demo_files"
RAANANA = 8700


# --- Clearing -------------------------------------------------------------------------


async def _delete_projects(db: AsyncSession, project_ids: list[uuid.UUID]) -> None:
    if not project_ids:
        return
    await db.execute(delete(AuditLog).where(AuditLog.project_id.in_(project_ids)))
    for pid in project_ids:
        await db.execute(
            text("DELETE FROM stored_files WHERE key LIKE :p"), {"p": f"projects/{pid}/%"}
        )
    # Requirements, documents, mail, suggestions, requests… go with the project (cascade).
    await db.execute(delete(Project).where(Project.id.in_(project_ids)))


async def _owned_projects(db: AsyncSession, user: User) -> list[uuid.UUID]:
    return list(
        await db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id))
    )


async def _remove_account(db: AsyncSession, user: User) -> None:
    await _delete_projects(db, await _owned_projects(db, user))
    orgs = list(
        await db.scalars(select(Membership.organization_id).where(Membership.user_id == user.id))
    )
    await db.execute(
        delete(AuditLog).where(or_(AuditLog.user_id == user.id, AuditLog.organization_id.in_(orgs)))
    )
    await db.execute(delete(Organization).where(Organization.id.in_(orgs)))
    await db.delete(user)


# --- Building -------------------------------------------------------------------------


async def _step(
    db: AsyncSession, project: Project, key: str, floor: int | None = None
) -> Requirement:
    query = (
        select(Requirement)
        .join(TemplateRequirement, TemplateRequirement.id == Requirement.template_requirement_id)
        .where(Requirement.project_id == project.id, TemplateRequirement.key == key)
    )
    if floor is not None:
        query = query.where(Requirement.floor == floor)
    step = await db.scalar(query.limit(1))
    assert step is not None, key
    return step


async def _file(
    db: AsyncSession,
    project: Project,
    requirement: Requirement | None,
    name: str,
    source_file: str,
    *,
    by: User | None = None,
    uploader: str | None = None,
    request: DocumentRequest | None = None,
    when: datetime | None = None,
) -> Document:
    data = (FILES / source_file).read_bytes()
    document = Document(
        id=uuid.uuid4(),
        project_id=project.id,
        requirement_id=requirement.id if requirement else None,
        file_name=name,
        content_type="application/pdf",
        size_bytes=len(data),
        source=DocumentSource.professional if request else DocumentSource.upload,
        status=DocumentStatus.ready,
        uploaded_by=by.id if by else None,
        uploader_name=uploader,
        request_id=request.id if request else None,
    )
    if when:
        document.created_at = when
    document.storage_key = document_key(project.id, document.id)
    await get_storage().put(document.storage_key, data, "application/pdf")
    db.add(document)
    await db.commit()
    return document


def _mail(
    sender: str, to: str, subject: str, body: str, day: datetime, attachment: tuple[str, str] | None
) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Date"] = format_datetime(day)
    msg["Message-ID"] = f"<demo-{uuid.uuid4().hex}@demo.arba.local>"
    msg.set_content(body)
    if attachment:
        name, source_file = attachment
        msg.add_attachment(
            (FILES / source_file).read_bytes(), maintype="application", subtype="pdf", filename=name
        )
    return msg.as_bytes()


async def build(db: AsyncSession, user: User) -> Project:
    storage = get_storage()
    now = datetime.now(UTC)
    template_id = await db.scalar(
        text("SELECT id FROM templates WHERE key = 'private_house' ORDER BY version DESC LIMIT 1")
    )
    project = await create_project(
        db,
        user,
        ProjectCreate(
            name="הבית של משפחת לוי",
            template_id=template_id,
            locality_code=RAANANA,
            address="רחוב אחוזה 120, רעננה",
            floors=2,
            gush="6587",
            helka="112",
            plot_number="57",
            permit_number="20250412",
            permit_request_number="1022334455",
            permit_issue_date=date(2025, 11, 10),
            permit_committee="הוועדה המקומית לתכנון ובנייה רעננה",
        ),
    )

    # The permit: filed, checked, and confirmed on the committee's site.
    await _file(
        db,
        project,
        await _step(db, project, "permit"),
        "היתר בנייה 20250412.pdf",
        "permit.pdf",
        by=user,
    )
    await run_checks(db, project, user)
    await confirm_with_committee(db, project, user)

    # Its conditions: two became steps, one joined the water step, one waits for approval.
    proposals = [
        (
            "2",
            "מינוי מהנדס אחראי לביקורת על הביצוע",
            "לפני תחילת עבודות יש למנות מהנדס אחראי לביקורת על הביצוע.",
            ConditionTiming.before_work,
            "pre",
            AuthorityType.supervising_engineer,
            ["כתב מינוי מהנדס אחראי"],
            "roles",
        ),
        (
            "3",
            "שמירה על עץ האלון בחזית המגרש",
            "שמירה על עץ האלון הקיים בחזית המגרש לפי הנחיות פקיד היערות.",
            ConditionTiming.before_form4,
            "form4",
            AuthorityType.municipality,
            ["אישור פקיד היערות"],
            None,
        ),
        (
            "4",
            "אישור תאגיד המים על חיבור לביוב",
            "לפני מתן תעודת גמר יש להציג אישור תאגיד המים על חיבור למערכת הביוב.",
            ConditionTiming.before_form4,
            "form4",
            AuthorityType.water_corporation,
            ["אישור חיבור לביוב"],
            "water_corp",
        ),
        (
            "5",
            "אישור יועץ בטיחות אש על גלאי עשן",
            "לפני טופס 4 יש להציג אישור יועץ בטיחות אש על התקנת גלאי עשן.",
            ConditionTiming.before_form4,
            "form4",
            AuthorityType.fire_department,
            ["אישור יועץ בטיחות אש"],
            None,
        ),
    ]
    conditions = []
    for number, title, body, timing, stage, authority, docs, match in proposals:
        condition = PermitCondition(
            project_id=project.id,
            number=number,
            text=body,
            title=title,
            timing=timing,
            stage=stage,
            authority_type=authority,
            documents=docs,
            match_requirement_id=(await _step(db, project, match)).id if match else None,
            source="claude",
        )
        db.add(condition)
        conditions.append(condition)
    project.conditions_status = "ready"
    await db.commit()
    for condition in conditions[1:]:
        await conditions_service.accept(db, project, user, condition.id)

    # Where the build stands: everything before the frame is done; floor 1 is under way.
    await catch_up(db, project, user, "skeleton")
    await _file(
        db,
        project,
        await _step(db, project, "plans"),
        "תיק תוכניות מאושר.pdf",
        "plans.pdf",
        by=user,
    )
    # The foundations' concrete certificates are in; floor 1's are being collected.
    await _file(
        db,
        project,
        await _step(db, project, "concrete_foundations"),
        "תעודות בטון - יסודות.pdf",
        "concrete.pdf",
        by=user,
    )
    floor_1 = await _step(db, project, "concrete_floor", 1)
    await change_status(db, project, floor_1.id, S.in_progress, user)
    # The frame declaration for the Home Front Command file is what the engineer is asked for.
    declaration = await _step(db, project, "hfc_structure")

    # The team, and their answers through upload links.
    surveyor = await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.surveyor,
            name="משה כהן - מדידות",
            email="moshe@example.co.il",
            phone="052-5551234",
        ),
    )
    engineer = await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.structural_engineer,
            name="אבי מזרחי - הנדסת מבנים",
            email="avi@example.co.il",
        ),
    )
    await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.testing_lab, name="מעבדת בטון השרון", email="lab@example.co.il"
        ),
    )
    await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.contractor,
            name="א.ב. בנייה ופיתוח",
            email="office@example.co.il",
            phone="09-7771234",
        ),
    )

    marking = await _step(db, project, "marking")
    asked, _ = await create_request(
        db,
        project,
        user,
        RequestCreate(
            requirement_id=marking.id,
            contact_id=surveyor.id,
            documents=["מפת סימון"],
            note="בבקשה עם חתימה וחותמת",
        ),
    )
    await _file(
        db, project, marking, "מפת סימון.pdf", "survey.pdf", uploader=surveyor.name, request=asked
    )
    asked.status, asked.fulfilled_at = RequestStatus.fulfilled, now - timedelta(days=200)

    asked_rebar, _ = await create_request(
        db,
        project,
        user,
        RequestCreate(
            requirement_id=declaration.id,
            contact_id=engineer.id,
            documents=["תצהיר אחראי לביצוע השלד"],
        ),
    )
    await _file(
        db,
        project,
        declaration,
        "תצהיר אחראי שלד.pdf",
        "rebar_wrong.pdf",
        uploader=engineer.name,
        request=asked_rebar,
    )
    asked_rebar.status, asked_rebar.fulfilled_at = RequestStatus.fulfilled, now - timedelta(hours=3)
    await db.commit()

    # Arba checks every filed document (the engineer's has another parcel's number).
    while await check_pending(db, storage, project.id):
        pass

    # Mail that came in, waiting for one tap.
    inbox = project.inbox_address
    for raw in (
        _mail(
            "מעבדת בטון השרון <lab@example.co.il>",
            inbox,
            "תוצאות בדיקת בטון - יסודות - אחוזה 120 רעננה",
            "שלום,\nמצורפות תוצאות בדיקות הבטון ליציקת היסודות בגוש 6587 חלקה 112."
            " כל התוצאות תקינות.\nמעבדת בטון השרון",
            now - timedelta(days=1, hours=2),
            ("תוצאות בדיקת בטון - יסודות.pdf", "concrete.pdf"),
        ),
        _mail(
            "מי רעננה - מחלקת חיבורים <hibburim@example.co.il>",
            inbox,
            "בקשה להשלמת מסמכים - חיבור מים לבנייה",
            "שלום רב,\nלצורך חיבור מים לבנייה ברחוב אחוזה 120, רעננה (גוש 6587 חלקה 112)"
            " יש להשלים תוכנית אינסטלציה חתומה.\nבברכה, מחלקת חיבורים",
            now - timedelta(hours=5),
            None,
        ),
    ):
        message_id = await store_email(
            db, storage, project, parse_rfc822(raw, f"demo-{uuid.uuid4().hex}")
        )
        await db.commit()
        assert message_id
        await suggest_for_message(db, storage, RulesClassifier(), message_id, scan_id=None)

    # A letter to the water corporation, ready for approval.
    await create_draft(db, project, await _step(db, project, "water_corp"), announce=False)
    return project


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", help="new password for the demo account (default: generated)")
    parser.add_argument(
        "--remove-email", action="append", default=[], help="another account to delete"
    )
    args = parser.parse_args()
    password = args.password or f"arba-demo-{secrets.token_hex(3)}"

    async with SessionLocal() as db:
        for email in args.remove_email:
            other = await db.scalar(select(User).where(User.email == email.lower()))
            if other is not None:
                await _remove_account(db, other)
        user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
        assert user is not None, f"{DEMO_EMAIL} doesn't exist; register it in the app first"
        await _delete_projects(db, await _owned_projects(db, user))
        user.name = "דנה לוי"
        user.password_hash = hash_password(password)
        await db.commit()

        project = await build(db, user)
        print(f"demo project: {project.name} ({project.id})")
        print(f"login: {DEMO_EMAIL} / {password}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
