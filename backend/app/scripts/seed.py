"""Loads checklist templates and the official reference data (authorities, localities,
planning committees, curated contacts). Safe to re-run. Run: python -m app.scripts.seed"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project
from app.db.session import SessionLocal, engine
from app.modules.directory.form4_lists import apply_city_list
from app.modules.directory.reference import load_reference
from app.modules.templates.loader import seed_templates


async def seed(db: AsyncSession) -> list[str]:
    """Returns a line per part, for logs."""
    added = await seed_templates(db)
    reference = await load_reference(db)
    # Projects already open get their authority's latest Form 4 list too.
    steps = 0
    for project in await db.scalars(select(Project)):
        steps += await apply_city_list(db, project)
    await db.commit()
    return [
        "templates: " + (", ".join(added) if added else "up to date"),
        "reference data: " + ", ".join(f"{n} {k}" for k, n in reference.items()),
        f"city Form 4 lists: {steps} steps added to existing projects",
    ]


async def main() -> None:
    async with SessionLocal() as db:
        lines = await seed(db)
    await engine.dispose()
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
