import uuid

from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.core.enums import ProjectRole
from app.core.enums import RequirementStatus as S
from app.db.models import Project, Requirement
from app.modules.documents.service import document_counts
from app.modules.inbox.service import counts as inbox_counts
from app.modules.permits.service import permit_out
from app.modules.projects import service
from app.modules.projects.schemas import (
    BuildState,
    CriticalPath,
    NextSteps,
    Progress,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    RequirementList,
    RequirementOut,
    StageProgress,
    StatusUpdate,
    stages_of,
)
from app.modules.requirements import service as requirements_service
from app.modules.requirements.engine import DONE, EngineResult

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_out(project: Project, role: ProjectRole, build: BuildState) -> ProjectOut:
    fields = {f: getattr(project, f) for f in ProjectOut.model_fields if f not in ("role", "build")}
    return ProjectOut(**fields, role=role, build=build)


def _progress(requirements: list[Requirement]) -> Progress:
    return Progress(done=sum(r.status in DONE for r in requirements), total=len(requirements))


def _build_state(requirements: list[Requirement], result: EngineResult[uuid.UUID]) -> BuildState:
    groups: dict[tuple[str, int | None], list[Requirement]] = {}
    for r in requirements:
        groups.setdefault((r.stage, r.floor), []).append(r)
    stages = [
        StageProgress(
            stage=stage,
            floor=floor,
            done=sum(r.status in DONE for r in items),
            total=len(items),
            skipped=sum(r.status == S.not_applicable for r in items),
        )
        for (stage, floor), items in groups.items()
    ]
    by_id = {r.id: r for r in requirements}
    focus = by_id[result.critical_path[0]] if result.critical_path else None
    if focus is None:
        focus = next((r for r in requirements if r.status not in DONE), None)
    return BuildState(
        progress=_progress(requirements),
        stages=stages,
        focus_stage=focus.stage if focus else None,
        focus_floor=focus.floor if focus else None,
    )


async def _summarize(db: DB, project: Project, role: ProjectRole) -> ProjectOut:
    requirements, deps = await requirements_service.load_graph(db, project.id)
    result = requirements_service.run_engine(requirements, deps)
    return _project_out(project, role, _build_state(requirements, result))


def _requirement_out(
    r: Requirement,
    deps: dict[uuid.UUID, list[uuid.UUID]],
    result: EngineResult[uuid.UUID],
    critical: set[uuid.UUID],
    documents: dict[uuid.UUID, int],
) -> RequirementOut:
    return RequirementOut(
        id=r.id,
        stage=r.stage,
        title=r.title,
        description=r.description,
        authority_type=r.authority_type,
        channel=r.channel,
        estimated_days=r.estimated_days,
        floor=r.floor,
        required_documents=r.required_documents,
        optional=r.optional,
        is_form4_gate=r.is_form4_gate,
        order=r.order,
        status=r.status,
        status_changed_at=r.status_changed_at,
        completed_at=r.completed_at,
        depends_on=deps[r.id],
        blocked_by=result.blocked_by[r.id],
        on_critical_path=r.id in critical,
        document_count=documents.get(r.id, 0),
        origin=r.origin,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, db: DB, user: CurrentUser) -> ProjectOut:
    project = await service.create_project(db, user, data)
    return await _summarize(db, project, ProjectRole.owner)


@router.get("")
async def list_projects(db: DB, user: CurrentUser) -> list[ProjectOut]:
    # One graph load per project. Fine at today's scale; batch it if lists grow large.
    return [await _summarize(db, p, role) for p, role in await service.list_projects(db, user)]


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, db: DB, user: CurrentUser) -> ProjectDetail:
    project, role = await service.get_project_for_user(db, project_id, user)
    summary = await _summarize(db, project, role)
    return ProjectDetail(
        **summary.model_dump(),
        stages=stages_of(project),
        inbox=await inbox_counts(db, project.id),
        permit=await permit_out(db, project),
    )


@router.get("/{project_id}/requirements")
async def list_requirements(project_id: uuid.UUID, db: DB, user: CurrentUser) -> RequirementList:
    project, _ = await service.get_project_for_user(db, project_id, user)
    requirements, deps = await requirements_service.load_graph(db, project.id)
    result = requirements_service.run_engine(requirements, deps)
    critical = set(result.critical_path)
    counts = await document_counts(db, project.id)
    return RequirementList(
        stages=stages_of(project),
        requirements=[_requirement_out(r, deps, result, critical, counts) for r in requirements],
    )


@router.get("/{project_id}/next-steps")
async def next_steps(project_id: uuid.UUID, db: DB, user: CurrentUser) -> NextSteps:
    """What can be done now, what is waiting, and what blocks the way to Form 4."""
    project, _ = await service.get_project_for_user(db, project_id, user)
    requirements, deps = await requirements_service.load_graph(db, project.id)
    result = requirements_service.run_engine(requirements, deps)
    critical = set(result.critical_path)
    counts = await document_counts(db, project.id)
    out = {r.id: _requirement_out(r, deps, result, critical, counts) for r in requirements}

    def having(*statuses: S) -> list[RequirementOut]:
        return [out[r.id] for r in requirements if r.status in statuses]

    # Within each group, critical-path items first, then template order.
    def prioritized(items: list[RequirementOut]) -> list[RequirementOut]:
        return sorted(items, key=lambda r: (not r.on_critical_path, r.order, r.floor or 0))

    return NextSteps(
        ready=prioritized(having(S.ready)),
        active=prioritized(having(S.in_progress, S.needs_fix)),
        waiting=prioritized(having(S.waiting_for_authority)),
        blocked=prioritized(having(S.blocked)),
        critical_path=CriticalPath(
            requirement_ids=result.critical_path, remaining_days=result.remaining_days
        ),
        progress=_progress(requirements),
    )


@router.patch("/{project_id}/requirements/{requirement_id}/status")
async def update_requirement_status(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    data: StatusUpdate,
    db: DB,
    user: CurrentUser,
) -> RequirementOut:
    project, _ = await service.get_project_for_user(db, project_id, user, ProjectRole.manager)
    await requirements_service.change_status(db, project, requirement_id, data.status, user)
    requirements, deps = await requirements_service.load_graph(db, project.id)
    result = requirements_service.run_engine(requirements, deps)
    requirement = next(r for r in requirements if r.id == requirement_id)
    counts = await document_counts(db, project.id)
    return _requirement_out(requirement, deps, result, set(result.critical_path), counts)
