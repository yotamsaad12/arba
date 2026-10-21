import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RequirementStatus as S
from app.core.errors import AppError
from app.db.models import AuditLog, Dependency, Project, Requirement, User
from app.modules.requirements.engine import AUTOMATIC, EngineResult, Node, evaluate

# Starting, waiting on, or finishing a requirement all need its dependencies to be done.
NEEDS_DEPENDENCIES = frozenset({S.in_progress, S.waiting_for_authority, S.done})
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
    if new_status == S.not_applicable and not requirement.optional:
        raise AppError(422, "requirement_not_optional", "only optional requirements can be skipped")

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
    await db.commit()
