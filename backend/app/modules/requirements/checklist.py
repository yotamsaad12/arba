"""The Form 4 file as the team shapes it: their own items, edits, features, and the summary.

90% of every authority's list is the same, so a project starts from a template; each
authority's own items, the team's additions and imported lists make it exact.
"""

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Form4Track, RequirementOrigin
from app.core.enums import RequirementStatus as S
from app.core.errors import AppError, not_found
from app.db.models import AuditLog, Dependency, Project, Requirement, User
from app.modules.documents.service import document_counts
from app.modules.projects.schemas import (
    Form4File,
    ProjectUpdate,
    RequirementCreate,
    RequirementUpdate,
    TrackSummary,
)
from app.modules.requirements.engine import AUTOMATIC, DONE
from app.modules.requirements.service import (
    add_requirement,
    apply_automatic_statuses,
    load_graph,
    run_engine,
    sync_fulfilled,
)

# Removable: what people added or imported. Template items are marked "not needed" instead,
# so the file still shows the authority's standard list was considered.
_REMOVABLE = {RequirementOrigin.user, RequirementOrigin.authority_list}


def _audit(project: Project, user: User, action: str, requirement: Requirement, **after: object):
    return AuditLog(
        organization_id=project.organization_id,
        project_id=project.id,
        user_id=user.id,
        action=action,
        entity="requirement",
        entity_id=requirement.id,
        after={"title": requirement.title, **{k: str(v) for k, v in after.items()}},
    )


async def _get(db: AsyncSession, project: Project, requirement_id: uuid.UUID) -> Requirement:
    requirement = await db.get(Requirement, requirement_id)
    if requirement is None or requirement.project_id != project.id:
        raise not_found("requirement")
    return requirement


async def create_item(
    db: AsyncSession,
    project: Project,
    user: User,
    data: RequirementCreate,
    origin: RequirementOrigin = RequirementOrigin.user,
    origin_ref: str | None = None,
) -> Requirement:
    requirement = await add_requirement(
        db,
        project,
        stage=data.stage,
        title=data.title,
        description=data.description,
        authority_type=data.authority_type,
        documents=data.documents,
        origin=origin,
        origin_ref=origin_ref or f"user:{uuid.uuid4().hex[:8]}",
    )
    requirement.track = data.track
    requirement.appendix = data.appendix
    requirement.standard = data.standard
    requirement.due_date = data.due_date
    requirement.notes = data.notes
    db.add(_audit(project, user, "requirement.added", requirement, track=data.track))
    await db.commit()
    return requirement


async def update_item(
    db: AsyncSession,
    project: Project,
    user: User,
    requirement_id: uuid.UUID,
    data: RequirementUpdate,
) -> Requirement:
    requirement = await _get(db, project, requirement_id)
    for field in data.model_fields_set:
        value = getattr(data, field)
        if field == "title" and value is None:
            continue
        setattr(requirement, "required_documents" if field == "documents" else field, value)
    db.add(
        _audit(
            project, user, "requirement.edited", requirement, fields=sorted(data.model_fields_set)
        )
    )
    await db.commit()
    return requirement


async def delete_item(
    db: AsyncSession, project: Project, user: User, requirement_id: uuid.UUID
) -> None:
    requirement = await _get(db, project, requirement_id)
    if requirement.origin not in _REMOVABLE:
        raise AppError(
            409, "template_item", "standard items can't be removed; mark them not needed instead"
        )
    await db.execute(
        delete(Dependency).where(
            or_(
                Dependency.requirement_id == requirement.id,
                Dependency.depends_on_id == requirement.id,
            )
        )
    )
    db.add(_audit(project, user, "requirement.removed", requirement))
    await db.delete(requirement)
    await db.flush()
    requirements, deps = await load_graph(db, project.id)
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    await db.commit()


async def update_project(
    db: AsyncSession, project: Project, user: User, data: ProjectUpdate
) -> Project:
    fields = data.model_fields_set - {"features"}
    for field in fields:
        setattr(project, field, getattr(data, field))
    if data.features is not None:
        project.features = [f.value for f in data.features]
        await _apply_features(db, project)
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="project.updated",
            entity="project",
            entity_id=project.id,
            after={"fields": sorted(data.model_fields_set), "features": project.features},
        )
    )
    await db.commit()
    return project


async def _apply_features(db: AsyncSession, project: Project) -> None:
    """Items that depend on features follow them, unless a person already decided: work under
    way or done stays, and "not needed" set by a person (it has a change time; the features'
    own "not needed" doesn't) stays."""
    features = set(project.features or [])
    requirements, deps = await load_graph(db, project.id)
    for r in requirements:
        if not r.applies_if:
            continue
        applies = set(r.applies_if) <= features
        if applies and r.status == S.not_applicable and r.status_changed_at is None:
            r.status = S.not_started
        elif not applies and r.status in AUTOMATIC:
            r.status, r.status_changed_at = S.not_applicable, None
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    sync_fulfilled(requirements)


async def form4_file(db: AsyncSession, project: Project) -> Form4File:
    requirements = list(
        await db.scalars(select(Requirement).where(Requirement.project_id == project.id))
    )
    files = await document_counts(db, project.id)
    tracks: list[TrackSummary] = []
    for track in Form4Track:
        items = [r for r in requirements if r.track == track]
        if not items:
            continue
        done = sum(r.status in DONE for r in items)
        tracks.append(
            TrackSummary(
                track=track,
                total=len(items),
                done=done,
                with_files=sum(1 for r in items if r.status not in DONE and files.get(r.id)),
                fulfils=[r.id for r in requirements if r.fulfilled_by_track == track],
                complete=done == len(items),
            )
        )
    return Form4File(
        tracks=tracks,
        total=len(requirements),
        done=sum(r.status in DONE for r in requirements),
    )
