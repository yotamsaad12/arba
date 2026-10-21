"""Loads checklist templates from YAML files into the database."""

import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuthorityType, Channel, ClientType, DependencyKind, Repeat
from app.db.models import Template, TemplateDependency, TemplateRequirement
from app.modules.requirements.engine import check_acyclic

TEMPLATE_DIR = Path(__file__).parent / "data"


class StageDef(BaseModel):
    key: str
    title: str
    description: str | None = None


class RequirementDef(BaseModel):
    key: str
    stage: str
    title: str
    description: str | None = None
    authority: AuthorityType
    channel: Channel
    days: int = Field(default=1, ge=0)
    repeat: Repeat = Repeat.none
    documents: list[str] = []
    optional: bool = False
    gate: bool = False
    depends_on: list[str] = []
    previous_floor: list[str] = []


class TemplateFile(BaseModel):
    key: str
    version: int
    name: str
    description: str | None = None
    client_type: ClientType
    building_type: str
    municipality: str | None = None
    stages: list[StageDef]
    requirements: list[RequirementDef]

    @model_validator(mode="after")
    def _check_references(self) -> "TemplateFile":
        stage_keys = {s.key for s in self.stages}
        by_key: dict[str, RequirementDef] = {}
        for r in self.requirements:
            if r.key in by_key:
                raise ValueError(f"duplicate requirement key: {r.key}")
            if r.stage not in stage_keys:
                raise ValueError(f"{r.key}: unknown stage {r.stage}")
            by_key[r.key] = r
        for r in self.requirements:
            for d in r.depends_on + r.previous_floor:
                if d not in by_key:
                    raise ValueError(f"{r.key}: unknown dependency {d}")
            for d in r.previous_floor:
                if r.repeat != Repeat.per_floor or by_key[d].repeat != Repeat.per_floor:
                    raise ValueError(f"{r.key}: previous_floor needs per_floor on both sides")
        # previous_floor edges point backwards across floors, so only same-floor edges can loop.
        check_acyclic({r.key: r.depends_on for r in self.requirements})
        return self


def parse_template_file(path: Path) -> TemplateFile:
    return TemplateFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def build_template(spec: TemplateFile) -> tuple[Template, list[TemplateDependency]]:
    template = Template(
        id=uuid.uuid4(),
        key=spec.key,
        version=spec.version,
        name=spec.name,
        description=spec.description,
        client_type=spec.client_type,
        building_type=spec.building_type,
        municipality=spec.municipality,
        stages=[s.model_dump() for s in spec.stages],
    )
    rows: dict[str, TemplateRequirement] = {}
    for order, r in enumerate(spec.requirements):
        rows[r.key] = TemplateRequirement(
            id=uuid.uuid4(),
            key=r.key,
            stage=r.stage,
            title=r.title,
            description=r.description,
            authority_type=r.authority,
            channel=r.channel,
            estimated_days=r.days,
            repeat=r.repeat,
            required_documents=r.documents,
            optional=r.optional,
            is_form4_gate=r.gate,
            order=order,
        )
    template.requirements = list(rows.values())
    dependencies = [
        TemplateDependency(
            template_id=template.id,
            requirement_id=rows[r.key].id,
            depends_on_id=rows[d].id,
            kind=kind,
        )
        for r in spec.requirements
        for kind, keys in (
            (DependencyKind.same, r.depends_on),
            (DependencyKind.previous_floor, r.previous_floor),
        )
        for d in keys
    ]
    return template, dependencies


async def seed_templates(db: AsyncSession) -> list[str]:
    """Inserts template versions that aren't in the database yet. Returns the keys added."""
    added: list[str] = []
    for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
        spec = parse_template_file(path)
        exists = await db.scalar(
            select(Template.id).where(Template.key == spec.key, Template.version == spec.version)
        )
        if exists:
            continue
        template, dependencies = build_template(spec)
        db.add(template)
        # Dependencies reference requirements but have no ORM relationship to them.
        await db.flush()
        db.add_all(dependencies)
        added.append(f"{spec.key}@v{spec.version}")
    await db.commit()
    return added
