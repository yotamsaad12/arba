"""Loads checklist templates and the official reference data (authorities, localities,
planning committees, curated contacts). Safe to re-run. Run: python -m app.scripts.seed"""

import asyncio

from sqlalchemy import select

from app.db.models import Project
from app.db.session import SessionLocal, engine
from app.modules.directory.form4_lists import apply_city_list
from app.modules.directory.reference import load_reference
from app.modules.templates.loader import seed_templates


async def main() -> None:
    async with SessionLocal() as db:
        added = await seed_templates(db)
        reference = await load_reference(db)
        # Projects already open get their authority's latest Form 4 list too.
        steps = 0
        for project in await db.scalars(select(Project)):
            steps += await apply_city_list(db, project)
        await db.commit()
    await engine.dispose()
    print("templates: " + (", ".join(added) if added else "up to date"))
    print("reference data: " + ", ".join(f"{n} {k}" for k, n in reference.items()))
    print(f"city Form 4 lists: {steps} steps added to existing projects")


if __name__ == "__main__":
    asyncio.run(main())
