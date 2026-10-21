import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.deps import DB, CurrentUser
from app.core.enums import ClientType
from app.db.models import Template, TemplateRequirement

router = APIRouter(prefix="/templates", tags=["templates"])


class TemplateOut(BaseModel):
    id: uuid.UUID
    key: str
    version: int
    name: str
    description: str | None
    client_type: ClientType
    building_type: str
    municipality: str | None
    requirement_count: int


@router.get("")
async def list_templates(db: DB, _: CurrentUser) -> list[TemplateOut]:
    # Latest version of each template only.
    latest = (
        select(Template.key, func.max(Template.version).label("version"))
        .group_by(Template.key)
        .subquery()
    )
    counts = (
        select(TemplateRequirement.template_id, func.count().label("n"))
        .group_by(TemplateRequirement.template_id)
        .subquery()
    )
    rows = await db.execute(
        select(Template, func.coalesce(counts.c.n, 0))
        .join(latest, (latest.c.key == Template.key) & (latest.c.version == Template.version))
        .outerjoin(counts, counts.c.template_id == Template.id)
        .order_by(Template.name)
    )
    return [
        TemplateOut(
            id=t.id,
            key=t.key,
            version=t.version,
            name=t.name,
            description=t.description,
            client_type=t.client_type,
            building_type=t.building_type,
            municipality=t.municipality,
            requirement_count=n,
        )
        for t, n in rows
    ]
