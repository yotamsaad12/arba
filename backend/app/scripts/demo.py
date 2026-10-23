"""Resets the demo accounts to rich, consistent projects for showing Arba to customers.

    python -m app.scripts.demo [--password PASSWORD] [--remove-email EMAIL ...]

Deletes the demo user's projects (and the projects and accounts of any --remove-email), then
builds "the Levi family's house" in Raanana, halfway through the frame: permit verified, its
conditions read, early stages done with real documents, a team of professionals, a request
answered through an upload link, a document Arba flagged, mail waiting for approval and a
letter to the water corporation. Everything goes through Arba's own services, so the data is
what the app itself would produce. Safe to run again before every demo.

A second account, for construction companies, gets "Nahal Park, plot 212" in Beer Sheva: two
residential buildings, 48 units, deep in the Form 4 file. Its Home Front Command file is half
in, a lab report for the wrong plot is flagged, its fire file is under way, and the
municipality's own list (an Excel sheet) waits for the person to approve where each item goes.

Point it at the target database with ARBA_DATABASE_URL and run it with
ARBA_STORAGE_BACKEND=database for a serverless deployment.
"""

import argparse
import asyncio
import io
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

import openpyxl
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AuthorityType,
    ClientType,
    ConditionTiming,
    DocumentSource,
    DocumentStatus,
    Form4Track,
    OrgRole,
    ProjectFeature,
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
from app.modules.projects.schemas import ProjectCreate, RequirementCreate
from app.modules.projects.service import create_project
from app.modules.requirements import list_import
from app.modules.requirements.checklist import create_item
from app.modules.requirements.service import change_status
from app.modules.suggestions.service import RulesClassifier, suggest_for_message
from app.modules.team.schemas import ContactIn, RequestCreate
from app.modules.team.service import add_contact, create_request

DEMO_EMAIL = "demo@example.com"
DEVELOPER_EMAIL = "developer@example.com"
FILES = Path(__file__).parent / "demo_files"
RAANANA = 8700
BEER_SHEVA = 9000


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
    db: AsyncSession,
    project: Project,
    key: str,
    floor: int | None = None,
    building: int | None = None,
) -> Requirement:
    query = (
        select(Requirement)
        .join(TemplateRequirement, TemplateRequirement.id == Requirement.template_requirement_id)
        .where(Requirement.project_id == project.id, TemplateRequirement.key == key)
    )
    if floor is not None:
        query = query.where(Requirement.floor == floor)
    if building is not None:
        query = query.where(Requirement.building == building)
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


async def _set(
    db: AsyncSession, project: Project, user: User, key: str, status: S, building: int | None = None
) -> None:
    step = await _step(db, project, key, building=building)
    await change_status(db, project, step.id, status, user)


def _municipality_list() -> bytes:
    """The municipality's Form 4 list as such lists come: a sheet with a status column."""
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "עירייה"
    sheet.append(["רשימת אישורים לטופס 4 - פארק הנחל, מגרש 212"])
    sheet.append(["מס'", "הבדיקה", "סטטוס"])
    for row in (
        (1, "תכנית עדות - מודד מוסמך", "נספח 20"),
        (2, "אישור חשמלאי מוסמך", "נספח 33"),
        (3, "אישור תאורת התמצאות", "נספח 41"),
        (4, "חישובי שטחים", "נספח 12"),
        (5, "אישור מחלקת גנים ונוף", "לתאם סיור עם המחלקה"),
        (6, "אישור מחלקת תברואה לחדרי אשפה", "נספח 37"),
        (7, "שילוט מספרי בניינים ודירות", ""),
        (8, "אישור yes", "אין צורך"),
    ):
        sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def build_developer(db: AsyncSession, user: User) -> Project:
    storage = get_storage()
    now = datetime.now(UTC)
    dev = "developer/"
    template_id = await db.scalar(
        text(
            "SELECT id FROM templates WHERE key = 'residential_building' "
            "ORDER BY version DESC LIMIT 1"
        )
    )
    project = await create_project(
        db,
        user,
        ProjectCreate(
            name="פארק הנחל - מגרש 212",
            template_id=template_id,
            locality_code=BEER_SHEVA,
            address="שדרות הנחל 40, באר שבע",
            floors=9,
            gush="38021",
            helka="15",
            plot_number="212",
            buildings=2,
            units=48,
            features=[
                ProjectFeature.basement,
                ProjectFeature.elevator,
                ProjectFeature.gas,
                ProjectFeature.parking,
                ProjectFeature.sprinklers,
            ],
            permit_number="20240877",
            permit_request_number="2023115566",
            permit_issue_date=date(2025, 4, 2),
            permit_committee="הוועדה המקומית לתכנון ובנייה באר שבע",
        ),
    )
    await _file(
        db,
        project,
        await _step(db, project, "permit"),
        "היתר בנייה 20240877.pdf",
        dev + "permit.pdf",
        by=user,
    )
    await run_checks(db, project, user)

    # The frame is up in both buildings; the Home Front Command file is being collected.
    await catch_up(db, project, user, "mamad")
    # Catch-up leaves items that hang on a feature; the basement is long finished.
    for building in (1, 2):
        await _set(db, project, user, "concrete_basement", S.done, building=building)
    await _set(db, project, user, "radon", S.done)
    await _file(
        db,
        project,
        await _step(db, project, "concrete_foundations", building=1),
        "תעודות בטון - יסודות - בניין 1.pdf",
        dev + "concrete.pdf",
        by=user,
        when=now - timedelta(days=120),
    )
    for key in ("hfc_order", "hfc_structure", "hfc_concrete", "hfc_door_window", "hfc_sealing"):
        await _set(db, project, user, key, S.done, building=1)
    await _set(db, project, user, "hfc_plan_page", S.done)
    for key in ("hfc_order", "hfc_structure", "hfc_concrete"):
        await _set(db, project, user, key, S.done, building=2)
    for key in ("hfc_door_window", "hfc_ventilation"):
        await _set(db, project, user, key, S.in_progress, building=2)

    # The lab sent building 2's sealing test, but for another plot: Arba flags it.
    lab = await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.testing_lab,
            name="מעבדת הנגב לבדיקות בנייה",
            email="lab-negev@example.co.il",
            phone="08-6231234",
        ),
    )
    await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.supervising_engineer,
            name="אינג' שירה בן דוד - פיקוח",
            email="shira@example.co.il",
        ),
    )
    await add_contact(
        db,
        project,
        ContactIn(
            role=AuthorityType.surveyor, name="מדידות הדרום", email="survey-south@example.co.il"
        ),
    )
    sealing = await _step(db, project, "hfc_sealing", building=2)
    asked, _ = await create_request(
        db,
        project,
        user,
        RequestCreate(
            requirement_id=sealing.id,
            contact_id=lab.id,
            documents=['דוח בדיקת אטימות ממ"דים'],
            note="בניין 2, כל הדירות",
        ),
    )
    await _file(
        db,
        project,
        sealing,
        "בדיקת אטימות - בניין 2.pdf",
        dev + "sealing_wrong.pdf",
        uploader=lab.name,
        request=asked,
    )
    asked.status, asked.fulfilled_at = RequestStatus.fulfilled, now - timedelta(hours=2)

    # The fire file: fire doors approved, detection and sprinklers with the lab.
    fire_doors = await _step(db, project, "fire_doors")
    await _file(
        db,
        project,
        fire_doors,
        "אישור דלתות אש.pdf",
        dev + "fire_doors.pdf",
        uploader=lab.name,
        when=now - timedelta(days=6),
    )
    await change_status(db, project, fire_doors.id, S.done, user)
    for key in ("fire_detection", "fire_sprinklers", "fire_hose_design"):
        await _set(db, project, user, key, S.in_progress)
    await _set(db, project, user, "fire_gas_location", S.waiting_for_authority)
    for key in ("sanitary", "elevators", "electrical_engineer", "water_disinfection"):
        await _set(db, project, user, key, S.in_progress)
    await _set(db, project, user, "hot", S.not_applicable)

    # Something only this municipality asks for, added by the team, with a deadline.
    garden = await create_item(
        db,
        project,
        user,
        RequirementCreate(
            title="אישור אגרונום העירייה לשתילת עצים ברחוב",
            track=Form4Track.municipality,
            appendix="נספח 27",
            notes="סיור נקבע עם האגרונום",
            due_date=(now + timedelta(days=12)).date(),
        ),
    )
    await change_status(db, project, garden.id, S.in_progress, user)
    await db.commit()

    while await check_pending(db, storage, project.id):
        pass

    # The municipality's own list arrived; Arba has read it and waits for approval.
    await list_import.start_import(
        db,
        storage,
        project,
        user,
        file_name="רשימת דרישות לטופס 4 - עיריית באר שבע.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=_municipality_list(),
    )
    return project


async def _developer_account(db: AsyncSession, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == DEVELOPER_EMAIL))
    if user is None:
        user = User(id=uuid.uuid4(), email=DEVELOPER_EMAIL, name="", password_hash="")
        org = Organization(id=uuid.uuid4(), name="", type=ClientType.business)
        db.add_all([user, org])
        await db.flush()
        db.add(Membership(user_id=user.id, organization_id=org.id, role=OrgRole.owner))
    else:
        await _delete_projects(db, await _owned_projects(db, user))
        org = await db.scalar(
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user.id)
        )
        assert org is not None
    user.name = "רוני אברהם"
    user.password_hash = hash_password(password)
    org.name, org.type = 'אופק יזמות ובנייה בע"מ', ClientType.business
    await db.commit()
    return user


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

        developer = await _developer_account(db, password)
        project = await build_developer(db, developer)
        print(f"developer project: {project.name} ({project.id})")
        print(f"login: {DEVELOPER_EMAIL} / {password}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
