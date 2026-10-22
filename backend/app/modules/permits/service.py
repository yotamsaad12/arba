"""Checks that a project's building permit is real, current and from the right committee."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DocumentStatus, PermitStatus, RequirementStatus
from app.core.errors import AppError
from app.db.models import (
    AuditLog,
    Authority,
    Document,
    PlanningCommittee,
    Project,
    Requirement,
    TemplateRequirement,
    User,
)
from app.modules.directory.reference import same_name
from app.modules.permits.schemas import PermitCheck, PermitOut
from app.modules.requirements.service import change_status

# A permit lapses if work doesn't start within this many years of issue (statutory default; a
# committee can set otherwise, so the message says it's an estimate).
DEFAULT_VALIDITY_YEARS = 3


def _add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


async def permit_requirement(db: AsyncSession, project: Project) -> Requirement | None:
    return await db.scalar(
        select(Requirement)
        .join(TemplateRequirement, TemplateRequirement.id == Requirement.template_requirement_id)
        .where(Requirement.project_id == project.id, TemplateRequirement.key == "permit")
    )


async def _has_document(db: AsyncSession, requirement: Requirement | None) -> bool:
    if requirement is None:
        return False
    return bool(
        await db.scalar(
            select(Document.id)
            .where(
                Document.requirement_id == requirement.id,
                Document.status == DocumentStatus.ready,
            )
            .limit(1)
        )
    )


async def run_checks(db: AsyncSession, project: Project, user: User) -> None:
    """Recomputes the checks and status. When they pass, the permit requirement is done."""
    requirement = await permit_requirement(db, project)
    has_document = await _has_document(db, requirement)
    checks: list[PermitCheck] = [
        PermitCheck(
            check="document",
            ok=has_document,
            message="קובץ ההיתר הועלה" if has_document else "חסר קובץ ההיתר (PDF)",
        ),
        PermitCheck(
            check="number",
            ok=bool(project.permit_number),
            message=f"מספר היתר {project.permit_number}"
            if project.permit_number
            else "חסר מספר היתר",
        ),
        _validity(project),
        await _committee(db, project),
        PermitCheck(
            check="location",
            ok=project.locality_code is not None,
            message="המיקום זוהה ביישוב רשמי"
            if project.locality_code
            else "לא נבחר יישוב מהרשימה הרשמית",
        ),
    ]
    project.permit_checks = [c.model_dump() for c in checks]

    if project.permit_status != PermitStatus.committee_confirmed:
        if not has_document:
            project.permit_status = PermitStatus.pending_verification
        elif all(c.ok is not False for c in checks):
            project.permit_status = PermitStatus.document_checked
        else:
            project.permit_status = PermitStatus.needs_attention
    await db.commit()

    if (
        requirement is not None
        and project.permit_status
        in (PermitStatus.document_checked, PermitStatus.committee_confirmed)
        and requirement.status != RequirementStatus.done
    ):
        await change_status(db, project, requirement.id, RequirementStatus.done, user)


def _validity(project: Project) -> PermitCheck:
    today = date.today()
    if project.permit_valid_until:
        ok = project.permit_valid_until >= today
        return PermitCheck(
            check="validity",
            ok=ok,
            message=f"בתוקף עד {project.permit_valid_until:%d/%m/%Y}"
            if ok
            else f"פג תוקף ב-{project.permit_valid_until:%d/%m/%Y}",
        )
    if project.permit_issue_date:
        estimate = _add_years(project.permit_issue_date, DEFAULT_VALIDITY_YEARS)
        ok = estimate >= today
        return PermitCheck(
            check="validity",
            ok=ok,
            message=(
                f"הוצא ב-{project.permit_issue_date:%d/%m/%Y}; "
                + (f"בתוקף כנראה עד {estimate:%d/%m/%Y}" if ok else "כנראה פג תוקף (מעל 3 שנים)")
            ),
        )
    return PermitCheck(check="validity", ok=False, message="חסר תאריך הוצאה או תוקף")


async def _committee(db: AsyncSession, project: Project) -> PermitCheck:
    official = (
        await db.get(PlanningCommittee, project.committee_code) if project.committee_code else None
    )
    if official is None:
        return PermitCheck(check="committee", ok=None, message="לא ידוע איזו ועדה אחראית ליישוב")
    if not project.permit_committee:
        return PermitCheck(
            check="committee", ok=None, message=f"הוועדה האחראית ליישוב: {official.name}"
        )
    written = project.permit_committee
    # The permit says "הוועדה המקומית לתכנון ובנייה רעננה"; compare the place name part.
    place = written.split("ובנייה")[-1].split("ובניה")[-1]
    if same_name(place, official.name) or same_name(written, official.name):
        return PermitCheck(check="committee", ok=True, message=f"הוועדה תואמת: {official.name}")
    return PermitCheck(
        check="committee",
        ok=False,
        message=f'בהיתר רשומה "{written}", אבל היישוב שייך לוועדה {official.name}',
    )


async def confirm_with_committee(db: AsyncSession, project: Project, user: User) -> None:
    requirement = await permit_requirement(db, project)
    if not await _has_document(db, requirement):
        raise AppError(409, "permit_document_missing", "upload the permit before confirming it")
    project.permit_status = PermitStatus.committee_confirmed
    project.permit_confirmed_by = user.id
    project.permit_confirmed_at = datetime.now(UTC)
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="permit.committee_confirmed",
            entity="project",
            entity_id=project.id,
        )
    )
    await db.commit()
    await run_checks(db, project, user)


async def permit_out(db: AsyncSession, project: Project) -> PermitOut:
    official = (
        await db.get(PlanningCommittee, project.committee_code) if project.committee_code else None
    )
    authority = (
        await db.scalar(select(Authority).where(Authority.committee_code == official.code))
        if official
        else None
    )
    requirement = await permit_requirement(db, project)
    return PermitOut(
        status=project.permit_status,
        number=project.permit_number,
        request_number=project.permit_request_number,
        issue_date=project.permit_issue_date,
        valid_until=project.permit_valid_until,
        committee_on_permit=project.permit_committee,
        official_committee=official.name if official else None,
        checks=[PermitCheck(**c) for c in project.permit_checks or []],
        confirmed_at=project.permit_confirmed_at,
        search_url=authority.permit_search_url if authority else None,
        committee_website=authority.website if authority else None,
        requirement_id=requirement.id if requirement else None,
    )
