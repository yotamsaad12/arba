from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings


def make_engine(url: str) -> AsyncEngine:
    """An engine for local Postgres or a hosted one (Neon on Vercel).

    Hosted URLs carry libpq options asyncpg doesn't take (sslmode, channel_binding); they
    become asyncpg's ssl argument. Through a connection pooler (PgBouncer, Neon's "-pooler"
    hosts) prepared statements can't be cached. Serverless functions keep no pool between
    invocations.
    """
    parsed = make_url(url)
    query: dict[str, Any] = dict(parsed.query)
    connect_args: dict[str, Any] = {}
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = "require"
    if "pooler" in (parsed.host or "") or query.pop("pgbouncer", None):
        connect_args["statement_cache_size"] = 0
        query["prepared_statement_cache_size"] = "0"
    parsed = parsed.set(query=query)
    if settings.serverless:
        return create_async_engine(parsed, connect_args=connect_args, poolclass=NullPool)
    return create_async_engine(parsed, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
