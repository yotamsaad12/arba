"""Loads checklist templates and the official reference data (authorities, localities,
planning committees, curated contacts). Safe to re-run. Run: python -m app.scripts.seed"""

import asyncio

from app.db.session import SessionLocal, engine
from app.modules.directory.reference import load_reference
from app.modules.templates.loader import seed_templates


async def main() -> None:
    async with SessionLocal() as db:
        added = await seed_templates(db)
        reference = await load_reference(db)
    await engine.dispose()
    print("templates: " + (", ".join(added) if added else "up to date"))
    print("reference data: " + ", ".join(f"{n} {k}" for k, n in reference.items()))


if __name__ == "__main__":
    asyncio.run(main())
