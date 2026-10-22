"""Serverless hosting has no deploy hook to run migrations from: the API brings its own
database up to date on the first request each instance serves.

Migrations run under a Postgres advisory lock, so instances starting together take turns.
Reference data (templates, localities, contacts, authority lists) is loaded again only when
its files changed, recognised by a fingerprint kept in app_meta.
"""

import asyncio
import hashlib
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import settings
from app.db.models import AppMeta
from app.db.session import SessionLocal, make_engine

log = logging.getLogger(__name__)

BACKEND = Path(__file__).resolve().parents[2]
DATA_DIRS = [
    BACKEND / "app" / "modules" / "templates" / "data",
    BACKEND / "app" / "modules" / "directory" / "data",
]
_LOCK_ID = 727_4  # arbitrary, constant across deploys
_ready = False
_guard = asyncio.Lock()


def data_fingerprint() -> str:
    digest = hashlib.sha256()
    for directory in DATA_DIRS:
        for path in sorted(directory.iterdir()):
            if path.is_file():
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def _migrate(url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    config.attributes["url"] = url
    command.upgrade(config, "head")


async def ensure_ready() -> None:
    global _ready
    if _ready:
        return
    async with _guard:
        if _ready:
            return
        # Session-level advisory locks need a direct connection, not a transaction pooler.
        url = settings.database_url_direct or settings.database_url
        engine = make_engine(url)
        try:
            async with engine.connect() as lock:
                await lock.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _LOCK_ID})
                try:
                    await asyncio.to_thread(_migrate, url)
                    await _seed_if_changed()
                finally:
                    await lock.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _LOCK_ID})
        finally:
            await engine.dispose()
        _ready = True


async def _seed_if_changed() -> None:
    from app.scripts.seed import seed

    fingerprint = data_fingerprint()
    async with SessionLocal() as db:
        current = await db.get(AppMeta, "reference_data")
        if current is not None and current.value == fingerprint:
            return
        for line in await seed(db):
            log.info("bootstrap: %s", line)
        await db.merge(AppMeta(key="reference_data", value=fingerprint))
        await db.commit()
