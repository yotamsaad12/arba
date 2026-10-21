import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import PROJECT_ROLE_RANK, DependencyKind, ProjectRole, Repeat, RequirementStatus
from app.core.errors import AppError, forbidden, not_found
from app.db.models import (
    AuditLog,
    Dependency,
    Membership,
    Project,
    ProjectMember,
    Requirement,
    Template,
    TemplateRequirement,
    User,
)
from app.modules.projects.schemas import ProjectCreate
from app.modules.requirements.service import apply_automatic_statuses, run_engine

# No 0/o/1/l/i, so inbox addresses survive being read out over the phone.
_SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_slug() -> str:
    # Random rather than derived from the name: inbox addresses shouldn't be guessable.
    return "p-" + "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(8))


async def create_project(db: AsyncSession, user: User, data: ProjectCreate) -> Project:
    membership = await db.scalar(select(Membership).where(Membership.user_id == user.id))
    if membership is None:
        raise AppError(409, "no_organization", "user has no organization")
    template = await db.scalar(
        select(Template)
        .where(Template.id == data.template_id)
        .options(selectinload(Template.requirements), selectinload(Template.dependencies))
    )
    if template is None:
        raise not_found("template")

    slug = new_slug()
    project = Project(
        id=uuid.uuid4(),
        organization_id=membership.organization_id,
        template_id=template.id,
        name=data.name,
        slug=slug,
        address=data.address,
        municipality=data.municipality,
        building_type=template.building_type,
        client_type=membership.organization.type,
        floors=data.floors,
        gush=data.gush,
        helka=data.helka,
        permit_number=data.permit_number,
        permit_valid_until=data.permit_valid_until,
        inbox_address=f"{slug}@{settings.inbox_domain}",
    )
    db.add(project)
    # These tables have no ORM relationships between them, so flush parents before children.
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectRole.owner))

    requirements, deps = expand_template(template, project)
    apply_automatic_statuses(requirements, run_engine(requirements, deps))
    db.add_all(requirements)
    await db.flush()
    db.add_all(Dependency(requirement_id=c, depends_on_id=p) for c, ps in deps.items() for p in ps)

    db.add(
        AuditLog(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            action="project.created",
            entity="project",
            entity_id=project.id,
            after={"template": f"{template.key}@v{template.version}"},
        )
    )
    await db.commit()
    return project


def expand_template(
    template: Template, project: Project
) -> tuple[list[Requirement], dict[uuid.UUID, list[uuid.UUID]]]:
    """Copies template requirements into the project, one per floor where they repeat."""
    instances: dict[uuid.UUID, dict[int | None, Requirement]] = {}
    for tr in template.requirements:
        floors: list[int | None] = (
            list(range(1, project.floors + 1)) if tr.repeat == Repeat.per_floor else [None]
        )
        instances[tr.id] = {f: _instantiate(tr, project, f) for f in floors}

    deps: dict[uuid.UUID, list[uuid.UUID]] = {
        r.id: [] for per_floor in instances.values() for r in per_floor.values()
    }
    for td in template.dependencies:
        children, parents = instances[td.requirement_id], instances[td.depends_on_id]
        for floor, child in children.items():
            if td.kind == DependencyKind.previous_floor:
                targets = [parents[floor - 1]] if floor and floor - 1 in parents else []
            elif floor is not None and floor in parents:
                targets = [parents[floor]]
            else:
                targets = list(parents.values())
            deps[child.id].extend(p.id for p in targets)

    requirements = [r for per_floor in instances.values() for r in per_floor.values()]
    return requirements, deps


def _instantiate(tr: TemplateRequirement, project: Project, floor: int | None) -> Requirement:
    return Requirement(
        id=uuid.uuid4(),
        project_id=project.id,
        template_requirement_id=tr.id,
        stage=tr.stage,
        title=f"{tr.title} – קומה {floor}" if floor else tr.title,
        description=tr.description,
        authority_type=tr.authority_type,
        channel=tr.channel,
        estimated_days=tr.estimated_days,
        floor=floor,
        required_documents=list(tr.required_documents),
        optional=tr.optional,
        is_form4_gate=tr.is_form4_gate,
        order=tr.order,
        # Column defaults only apply at insert; the engine runs before that.
        status=RequirementStatus.not_started,
    )


async def list_projects(db: AsyncSession, user: User) -> list[tuple[Project, ProjectRole]]:
    rows = await db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return [(p, role) for p, role in rows]


async def get_project_for_user(
    db: AsyncSession,
    project_id: uuid.UUID,
    user: User,
    min_role: ProjectRole = ProjectRole.viewer,
) -> tuple[Project, ProjectRole]:
    row = (
        await db.execute(
            select(Project, ProjectMember.role)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(Project.id == project_id, ProjectMember.user_id == user.id)
            .options(selectinload(Project.template))
        )
    ).first()
    # Same 404 whether the project doesn't exist or belongs to someone else.
    if row is None:
        raise not_found("project")
    project, role = row
    if PROJECT_ROLE_RANK[role] < PROJECT_ROLE_RANK[min_role]:
        raise forbidden()
    return project, role
