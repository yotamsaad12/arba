import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuthorityType, Channel, RequirementOrigin
from app.core.enums import RequirementStatus as S
from app.core.errors import AppError
from app.db.models import AuditLog, Dependency, Project, Requirement, User
from app.modules.requirements.engine import AUTOMATIC, EngineResult, Node, evaluate

# The order of steps drives the timeline and the "waiting for" hints, not what a person may
# record: a document that arrived early is ticked when it arrives (authorities' own lists have
# no order). An item finished before what it depends on shows those as still open.
NEEDS_DEPENDENCIES: frozenset[S] = frozenset()
MANUAL_TARGETS = frozenset(
    {S.not_started, S.in_progress, S.waiting_for_authority, S.needs_fix, S.done, S.not_applicable}
)


async def load_graph(
    db: AsyncSession, project_id: uuid.UUID
) -> tuple[list[Requirement], dict[uuid.UUID, list[uuid.UUID]]]:
    requirements = list(
        await db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.order, Requirement.floor)
        )
    )
    deps: dict[uuid.UUID, list[uuid.UUID]] = {r.id: [] for r in requirements}
    rows = await db.execute(
        select(Dependency.requirement_id, Dependency.depends_on_id)
        .join(Requirement, Requirement.id == Dependency.requirement_id)
        .where(Requirement.project_id == project_id)
    )
    for child, parent in rows:
        deps[child].append(parent)
    return requirements, deps


def run_engine(
    requirements: list[Requirement], deps: dict[uuid.UUID, list[uuid.UUID]]
) -> EngineResult[uuid.UUID]:
    nodes = [Node(r.id, r.status, r.estimated_days, r.is_form4_gate) for r in requirements]
    return evaluate(nodes, deps)


def apply_automatic_statuses(
    requirements: list[Requirement], result: EngineResult[uuid.UUID]
) -> None:
    now = datetime.now(UTC)
    for r in requirements:
        new = result.statuses[r.id]
        if new != r.status:
            r.status = new
            r.status_changed_at = now


async def change_status(
    db: AsyncSession, project: Project, requirement_id: uuid.UUID, new_status: S, user: User
) -> None:
    requirements, deps = await load_graph(db, project.id)
    requirement = next((r for r in requirements if r.id == requirement_id), None)
    if requirement is None:
        raise AppError(404, "requirement_not_found", "requirement not found")

    if new_status not in MANUAL_TARGETS:
        raise AppError(422, "status_is_automatic", f"{new_status} is set by the system")
    # Any item can be "not needed": authorities' own lists say "אין צורך" freely.

    result = run_engine(requirements, deps)
    unmet = result.blocked_by[requirement.id]
    if new_status in NEEDS_DEPENDENCIES and unmet:
        raise AppError(
            409,
            "dependencies_not_done",
            "dependencies must be done first",
            {"blocked_by": [str(d) for d in unmet]},
        )

    before = requirement.status
    if new_status == before or (new_status == S.not_started and before in AUTOMATIC):
        return
    now = datetime.now(UTC)
    requirement.status = new_status
    requirement.status_changed_at = now
    requirement.completed_at = now if new_status == S.done else None
    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="requirement.status_changed",
            entity="requirement",
            entity_id=requirement.id,
            before={"status": before},
            after={"status": new_status},
        )
    )
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    sync_fulfilled(requirements)
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    await db.commit()


async def add_requirement(
    db: AsyncSession,
    project: Project,
    *,
    stage: str,
    title: str,
    description: str | None,
    authority_type: AuthorityType,
    documents: list[str],
    origin: RequirementOrigin,
    origin_ref: str,
    after: list[uuid.UUID] | None = None,
    optional: bool = False,
) -> Requirement:
    """Adds a step that isn't in the template (a permit condition, a city's own requirement).

    It comes after `after` and before the Form 4 submission, which now waits for it too.
    Flushes; the caller commits.
    """
    requirements, deps = await load_graph(db, project.id)
    in_stage = [r.order for r in requirements if r.stage == stage]
    requirement = Requirement(
        id=uuid.uuid4(),
        project_id=project.id,
        stage=stage,
        title=title[:300],
        description=description,
        authority_type=authority_type,
        channel=Channel.email,
        estimated_days=7,
        required_documents=documents,
        optional=optional,
        order=max(in_stage, default=max((r.order for r in requirements), default=0)) + 1,
        status=S.not_started,
        origin=origin,
        origin_ref=origin_ref,
    )
    db.add(requirement)
    await db.flush()
    new_deps = [Dependency(requirement_id=requirement.id, depends_on_id=p) for p in after or []]
    gates = [r for r in requirements if r.is_form4_gate]
    new_deps += [Dependency(requirement_id=g.id, depends_on_id=requirement.id) for g in gates]
    db.add_all(new_deps)
    await db.flush()

    requirements.append(requirement)
    deps[requirement.id] = list(after or [])
    for g in gates:
        deps[g.id].append(requirement.id)
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    return requirement


def sync_fulfilled(requirements: list[Requirement]) -> list[Requirement]:
    """Items another authority's file fulfils ("אישור הג"א" ← the Home Front Command file):
    done once every item on that file is done or not needed. Returns the items it completed."""
    by_track: dict[str, list[Requirement]] = {}
    for r in requirements:
        by_track.setdefault(r.track, []).append(r)
    completed = []
    now = datetime.now(UTC)
    for r in requirements:
        if r.fulfilled_by_track is None or r.status in (S.done, S.not_applicable):
            continue
        items = by_track.get(r.fulfilled_by_track, [])
        if items and all(i.status in (S.done, S.not_applicable) for i in items):
            r.status, r.status_changed_at, r.completed_at = S.done, now, now
            completed.append(r)
    return completed
