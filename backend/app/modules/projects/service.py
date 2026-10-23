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
from app.modules.directory.form4_lists import apply_city_list
from app.modules.directory.service import get_locality
from app.modules.permits.service import run_checks
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

    place = await get_locality(db, data.locality_code) if data.locality_code else None
    if data.locality_code and place is None:
        raise not_found("locality")

    slug = new_slug()
    project = Project(
        id=uuid.uuid4(),
        organization_id=membership.organization_id,
        template_id=template.id,
        name=data.name,
        slug=slug,
        address=data.address,
        # Shown as the place; the official codes below drive the directory.
        municipality=(place.name if place else data.municipality) or "",
        locality_code=place.code if place else None,
        municipality_code=place.municipality_code if place else None,
        committee_code=place.committee_code if place else None,
        permit_request_number=data.permit_request_number,
        permit_issue_date=data.permit_issue_date,
        permit_committee=data.permit_committee,
        building_type=template.building_type,
        client_type=membership.organization.type,
        floors=data.floors,
        gush=data.gush,
        helka=data.helka,
        permit_number=data.permit_number,
        permit_valid_until=data.permit_valid_until,
        plot_number=data.plot_number,
        buildings=data.buildings,
        units=data.units,
        features=[f.value for f in data.features],
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
    await db.flush()
    # The local authority's own Form 4 requirements, on top of the template.
    await apply_city_list(db, project)

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
    await run_checks(db, project, user)
    return project


def _copies(tr: TemplateRequirement, project: Project) -> list[int | None]:
    """Which copies of a template item the project gets: one per floor, per building, or one."""
    if tr.repeat == Repeat.per_floor:
        return list(range(1, project.floors + 1))
    if tr.repeat == Repeat.per_building:
        return list(range(1, max(project.buildings, 1) + 1))
    return [None]


def expand_template(
    template: Template, project: Project
) -> tuple[list[Requirement], dict[uuid.UUID, list[uuid.UUID]]]:
    """Copies template requirements into the project: per floor or per building where they
    repeat. Items for features the project doesn't have start as not applicable."""
    by_id = {tr.id: tr for tr in template.requirements}
    instances: dict[uuid.UUID, dict[int | None, Requirement]] = {
        tr.id: {n: _instantiate(tr, project, n) for n in _copies(tr, project)}
        for tr in template.requirements
    }

    deps: dict[uuid.UUID, list[uuid.UUID]] = {
        r.id: [] for copies in instances.values() for r in copies.values()
    }
    for td in template.dependencies:
        children, parents = instances[td.requirement_id], instances[td.depends_on_id]
        same_kind = by_id[td.requirement_id].repeat == by_id[td.depends_on_id].repeat
        for n, child in children.items():
            if td.kind == DependencyKind.previous_floor:
                targets = [parents[n - 1]] if n and n - 1 in parents else []
            elif n is not None and same_kind and n in parents:
                targets = [parents[n]]
            else:
                targets = list(parents.values())
            deps[child.id].extend(p.id for p in targets)

    requirements = [r for copies in instances.values() for r in copies.values()]
    return requirements, deps


def _instantiate(tr: TemplateRequirement, project: Project, n: int | None) -> Requirement:
    floor = n if tr.repeat == Repeat.per_floor else None
    building = n if tr.repeat == Repeat.per_building else None
    title = tr.title
    if floor:
        title = f"{tr.title} – קומה {floor}"
    elif building and project.buildings > 1:
        title = f"{tr.title} – בניין {building}"
    applies = set(tr.applies_if) <= set(project.features or [])
    return Requirement(
        id=uuid.uuid4(),
        project_id=project.id,
        template_requirement_id=tr.id,
        stage=tr.stage,
        title=title,
        description=tr.description,
        authority_type=tr.authority_type,
        channel=tr.channel,
        estimated_days=tr.estimated_days,
        floor=floor,
        building=building,
        required_documents=list(tr.required_documents),
        optional=tr.optional or bool(tr.applies_if),
        is_form4_gate=tr.is_form4_gate,
        order=tr.order,
        track=tr.track,
        appendix=tr.appendix,
        standard=tr.standard,
        applies_if=list(tr.applies_if),
        fulfilled_by_track=tr.fulfilled_by_track,
        # Column defaults only apply at insert; the engine runs before that.
        status=RequirementStatus.not_started if applies else RequirementStatus.not_applicable,
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
