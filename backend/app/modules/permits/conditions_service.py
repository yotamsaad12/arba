"""Permit conditions: reading them, proposing where each belongs, and applying approvals."""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    AuthorityType,
    ConditionStatus,
    DocumentStatus,
    RequirementOrigin,
)
from app.core.errors import AppError, not_found
from app.core.storage import Storage
from app.db.models import AuditLog, Document, PermitCondition, Project, Requirement, User
from app.db.session import SessionLocal
from app.modules.permits import conditions
from app.modules.permits.schemas import ConditionOut, ConditionsOut
from app.modules.permits.service import permit_requirement
from app.modules.projects.schemas import stages_of
from app.modules.requirements.service import add_requirement

log = logging.getLogger(__name__)

# Broad bodies: sharing the authority alone doesn't make two steps the same.
_TOO_BROAD = {AuthorityType.municipality, AuthorityType.contractor}


async def _permit_pdf(db: AsyncSession, storage: Storage, project: Project) -> bytes | None:
    requirement = await permit_requirement(db, project)
    if requirement is None:
        return None
    document = await db.scalar(
        select(Document)
        .where(
            Document.requirement_id == requirement.id,
            Document.status == DocumentStatus.ready,
            Document.content_type == "application/pdf",
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    return await storage.get(document.storage_key) if document else None


async def should_read(db: AsyncSession, storage: Storage, project: Project) -> bool:
    """True when there is a permit PDF whose conditions haven't been read yet."""
    return project.conditions_status is None and await _permit_pdf(db, storage, project) is not None


async def start(db: AsyncSession, project: Project) -> None:
    project.conditions_status = "reading"
    await db.commit()


async def read_in_background(project_id: uuid.UUID, storage: Storage) -> None:
    async with SessionLocal() as db:
        project = await db.scalar(
            select(Project).where(Project.id == project_id).options(selectinload(Project.template))
        )
        if project is None:
            return
        try:
            await _read(db, storage, project)
            project.conditions_status = "ready"
        except Exception:
            log.exception("reading permit conditions failed for %s", project_id)
            await db.rollback()
            project = await db.get(Project, project_id)
            assert project is not None
            project.conditions_status = "failed"
        await db.commit()


async def _read(db: AsyncSession, storage: Storage, project: Project) -> None:
    pdf = await _permit_pdf(db, storage, project)
    if pdf is None:
        return
    stage_keys = [s.key for s in stages_of(project)]
    requirements = list(
        await db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project.id)
            .order_by(Requirement.order, Requirement.floor)
        )
    )
    # One entry per step; floors repeat the same step.
    unique = [r for r in requirements if r.floor in (None, 1)]
    refs = {f"R{i + 1}": r for i, r in enumerate(unique)}
    found, source = await conditions.read(
        pdf,
        [{"key": s.key, "title": s.title} for s in stages_of(project)],
        [
            {"ref": ref, "stage": r.stage, "title": r.title, "authority": r.authority_type.value}
            for ref, r in refs.items()
        ],
    )

    # Reading again replaces what is still only proposed; decisions stay.
    await db.execute(
        delete(PermitCondition).where(
            PermitCondition.project_id == project.id,
            PermitCondition.status == ConditionStatus.proposed,
        )
    )
    decided = {
        c.text
        for c in await db.scalars(
            select(PermitCondition).where(PermitCondition.project_id == project.id)
        )
    }
    for c in found:
        if c.text in decided:
            continue
        match = refs.get(c.matches or "")
        if match is None and c.authority_type not in _TOO_BROAD:
            match = next(
                (r for r in unique if r.authority_type == c.authority_type and r.stage == c.stage),
                None,
            )
        db.add(
            PermitCondition(
                project_id=project.id,
                number=c.number,
                text=c.text,
                title=c.title or c.text[:80],
                timing=c.timing,
                stage=c.stage if c.stage in stage_keys else conditions.TIMING_STAGE[c.timing],
                authority_type=c.authority_type,
                documents=c.documents,
                match_requirement_id=match.id if match else None,
                source=source,
            )
        )
    await db.flush()


async def list_conditions(db: AsyncSession, project: Project) -> ConditionsOut:
    rows = list(
        await db.execute(
            select(PermitCondition, Requirement.title)
            .outerjoin(
                Requirement,
                Requirement.id.in_(
                    [PermitCondition.requirement_id, PermitCondition.match_requirement_id]
                ),
            )
            .where(PermitCondition.project_id == project.id)
            .order_by(PermitCondition.created_at, PermitCondition.number)
        )
    )
    seen: dict[uuid.UUID, ConditionOut] = {}
    for c, title in rows:
        if c.id in seen:
            continue
        seen[c.id] = ConditionOut(
            id=c.id,
            number=c.number,
            text=c.text,
            title=c.title,
            timing=c.timing,
            stage=c.stage,
            authority_type=c.authority_type,
            documents=c.documents,
            status=c.status,
            match_requirement_id=c.match_requirement_id,
            requirement_id=c.requirement_id,
            requirement_title=title,
            source=c.source,
        )
    return ConditionsOut(status=project.conditions_status, conditions=list(seen.values()))


async def _get(db: AsyncSession, project: Project, condition_id: uuid.UUID) -> PermitCondition:
    condition = await db.get(PermitCondition, condition_id)
    if condition is None or condition.project_id != project.id:
        raise not_found("condition")
    if condition.status != ConditionStatus.proposed:
        raise AppError(409, "condition_decided", "this condition was already handled")
    return condition


async def accept(
    db: AsyncSession,
    project: Project,
    user: User,
    condition_id: uuid.UUID,
    as_new: bool = False,
) -> None:
    """Applies Arba's proposal: add the documents to the matching step, or create a step.
    `as_new` makes a new step even when Arba proposed an existing one."""
    condition = await _get(db, project, condition_id)
    target = (
        await db.get(Requirement, condition.match_requirement_id)
        if condition.match_requirement_id and not as_new
        else None
    )
    if target is not None:
        siblings = list(
            await db.scalars(
                select(Requirement).where(
                    Requirement.project_id == project.id,
                    Requirement.template_requirement_id == target.template_requirement_id,
                )
            )
            if target.template_requirement_id
            else [target]
        )
        for r in siblings:
            r.required_documents = list(
                dict.fromkeys([*r.required_documents, *condition.documents])
            )
    else:
        permit_req = await permit_requirement(db, project)
        target = await add_requirement(
            db,
            project,
            stage=condition.stage,
            title=condition.title,
            description=f"תנאי בהיתר{f' (סעיף {condition.number})' if condition.number else ''}: "
            f"{condition.text}",
            authority_type=condition.authority_type,
            documents=condition.documents,
            origin=RequirementOrigin.permit_condition,
            origin_ref=str(condition.id),
            after=[permit_req.id] if permit_req else None,
        )
    condition.status = ConditionStatus.accepted
    condition.requirement_id = target.id
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="permit_condition.accepted",
            entity="permit_condition",
            entity_id=condition.id,
            after={"requirement": str(target.id), "new": target.origin_ref == str(condition.id)},
        )
    )
    await db.commit()


async def ignore(db: AsyncSession, project: Project, user: User, condition_id: uuid.UUID) -> None:
    condition = await _get(db, project, condition_id)
    condition.status = ConditionStatus.ignored
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="permit_condition.ignored",
            entity="permit_condition",
            entity_id=condition.id,
        )
    )
    await db.commit()


async def accept_all(db: AsyncSession, project: Project, user: User) -> int:
    ids = list(
        await db.scalars(
            select(PermitCondition.id).where(
                PermitCondition.project_id == project.id,
                PermitCondition.status == ConditionStatus.proposed,
            )
        )
    )
    for condition_id in ids:
        await accept(db, project, user, condition_id)
    return len(ids)
