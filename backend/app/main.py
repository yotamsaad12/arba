import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.v1 import (
    auth,
    catchup,
    cron,
    dev,
    directory,
    documents,
    inbox,
    me,
    outreach,
    permits,
    projects,
    public,
    storage,
    suggestions,
    team,
    templates,
    webhooks,
)
from app.core.config import settings
from app.core.errors import install_error_handlers


def _operation_id(route: APIRoute) -> str:
    # Stable, readable names for the generated TypeScript client.
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = None
    if settings.run_worker_in_api and settings.env != "test":
        from app.worker import run_forever

        task = asyncio.create_task(run_forever())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Arba API",
        version="0.1.0",
        generate_unique_id_function=_operation_id,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    if settings.serverless:
        from fastapi import Request

        from app.ai.client import store_identity_token
        from app.core.bootstrap import ensure_ready

        @app.middleware("http")
        async def _bootstrap(request: Request, call_next):  # type: ignore[no-untyped-def]
            # Vercel's identity token for this request: what Claude federation exchanges.
            store_identity_token(request.headers.get("x-vercel-oidc-token", ""))
            # First request on a fresh instance: migrate and load reference data once.
            if request.url.path.startswith("/api/"):
                await ensure_ready()
            return await call_next(request)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(templates.router)
    v1.include_router(projects.router)
    v1.include_router(documents.router)
    v1.include_router(inbox.router)
    v1.include_router(suggestions.router)
    v1.include_router(permits.router)
    v1.include_router(directory.router)
    v1.include_router(catchup.router)
    v1.include_router(outreach.router)
    v1.include_router(cron.router)
    v1.include_router(team.router)
    v1.include_router(public.router)
    v1.include_router(catchup.callbacks)
    v1.include_router(storage.router)
    v1.include_router(webhooks.router)
    v1.include_router(me.router)
    if settings.env in ("dev", "test") and settings.whatsapp_provider == "simulator":
        v1.include_router(dev.router)
    app.include_router(v1)

    @app.get("/health", include_in_schema=False)
    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
