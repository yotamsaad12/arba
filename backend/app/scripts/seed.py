"""Loads checklist templates into the database. Run: python -m app.scripts.seed"""

import asyncio

from app.db.session import SessionLocal, engine
from app.modules.templates.loader import seed_templates


async def main() -> None:
    async with SessionLocal() as db:
        added = await seed_templates(db)
    await engine.dispose()
    print("added: " + ", ".join(added) if added else "templates up to date")


if __name__ == "__main__":
    asyncio.run(main())
