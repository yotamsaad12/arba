import asyncio
from logging.config import fileConfig

from alembic import context

from app.core.config import settings
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.base import Base
from app.db.session import make_engine

config = context.config
if config.config_file_name is not None:
    # Keep the app's loggers working when migrations run inside the API (serverless).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
# The serverless bootstrap passes a direct (unpooled) URL; otherwise the app's own.
URL = config.attributes.get("url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = make_engine(URL)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
