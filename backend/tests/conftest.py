import os
import tempfile

# Must be set before the app (and its settings) are imported.
os.environ["ARBA_ENV"] = "test"
os.environ["ARBA_STORAGE_DIR"] = tempfile.mkdtemp(prefix="arba-test-storage-")
# Deterministic filing suggestions; the Claude path is tested with a fake client.
os.environ["ARBA_AI_PROVIDER"] = "rules"
os.environ["ARBA_EMAIL_BACKEND"] = "console"
os.environ["ARBA_WHATSAPP_PROVIDER"] = "simulator"
os.environ.setdefault(
    "ARBA_DATABASE_URL", "postgresql+asyncpg://arba:arba@localhost:5432/arba_test"
)

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.templates.loader import seed_templates  # noqa: E402

# Everything except templates is wiped between tests.
_PER_TEST_TABLES = [
    t.name for t in Base.metadata.sorted_tables if not t.name.startswith("template")
]


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await seed_templates(db)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean() -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_PER_TEST_TABLES)} CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(client: AsyncClient, email: str = "dana@example.com", **extra: object) -> str:
    body = {
        "name": "דנה כהן",
        "email": email,
        "password": "correct-horse",
        "client_type": "private",
        **extra,
    }
    response = await client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
