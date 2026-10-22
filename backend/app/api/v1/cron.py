"""Periodic work when there is no worker process (serverless): Vercel Cron calls this."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Header

from app.core.config import settings
from app.core.errors import AppError, not_found
from app.worker import tick

router = APIRouter(prefix="/cron", tags=["cron"], include_in_schema=False)


@router.get("/tick")
async def cron_tick(authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    """Morning summaries, due notifications, new requests and reminders to authorities.
    Vercel sends `Authorization: Bearer $CRON_SECRET`."""
    if not settings.cron_secret:
        raise not_found("route")
    if not secrets.compare_digest(authorization or "", f"Bearer {settings.cron_secret}"):
        raise AppError(401, "unauthenticated", "invalid cron secret")
    await tick()
    return {"status": "ok"}
