"""Local authorities' own Form 4 requirements, added to projects in their area."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuthorityType, RequirementOrigin
from app.db.models import Project, Requirement, TemplateRequirement
from app.modules.requirements.service import add_requirement

LISTS = Path(__file__).parent / "data" / "form4_lists.yaml"


@lru_cache
def _lists() -> dict[int, dict[str, Any]]:
    return {entry["municipality"]: entry for entry in yaml.safe_load(LISTS.read_text("utf-8"))}


def city_list(municipality_code: int | None) -> dict[str, Any] | None:
    return _lists().get(municipality_code) if municipality_code else None


async def apply_city_list(db: AsyncSession, project: Project) -> int:
    """Adds the authority's own requirements to the project. Safe to run again: steps added
    before are recognised, documents aren't listed twice. Returns the number of new steps.
    Flushes; the caller commits."""
    entry = city_list(project.municipality_code)
    if entry is None:
        return 0
    existing = set(
        await db.scalars(
            select(Requirement.origin_ref).where(
                Requirement.project_id == project.id,
                Requirement.origin == RequirementOrigin.city_list,
            )
        )
    )
    added = 0
    for item in entry["requirements"]:
        ref = f"{entry['municipality']}:{item['key']}"
        documents = list(item.get("documents") or [])
        if item.get("match"):
            steps = await db.scalars(
                select(Requirement)
                .join(
                    TemplateRequirement,
                    TemplateRequirement.id == Requirement.template_requirement_id,
                )
                .where(
                    Requirement.project_id == project.id, TemplateRequirement.key == item["match"]
                )
            )
            for step in steps:
                step.required_documents = list(
                    dict.fromkeys([*step.required_documents, *documents])
                )
            continue
        if ref in existing:
            continue
        await add_requirement(
            db,
            project,
            stage=item["stage"],
            title=item["title"],
            description=item.get("description"),
            authority_type=AuthorityType(item["authority"]),
            documents=documents,
            origin=RequirementOrigin.city_list,
            origin_ref=ref,
            optional=bool(item.get("optional")),
        )
        added += 1
    await db.flush()
    return added
