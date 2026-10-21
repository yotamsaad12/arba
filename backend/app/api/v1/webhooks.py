import hashlib
import json
import logging
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.deps import DB
from app.core.errors import AppError
from app.core.storage import get_storage
from app.db.models import InboundEmail
from app.db.session import SessionLocal
from app.email.processing import process_inbound, raw_key
from app.modules.suggestions.service import get_classifier, suggest_for_message

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"], include_in_schema=False)
_basic = HTTPBasic(auto_error=False)


def _check_credentials(credentials: HTTPBasicCredentials | None) -> None:
    ok = credentials is not None and all(
        [
            secrets.compare_digest(credentials.username, settings.inbound_webhook_user),
            secrets.compare_digest(credentials.password, settings.inbound_webhook_password),
        ]
    )
    if not ok:
        raise AppError(401, "unauthenticated", "invalid webhook credentials")


@router.post("/postmark/inbound")
async def postmark_inbound(
    request: Request,
    background: BackgroundTasks,
    db: DB,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> dict[str, str]:
    """Stores the delivery and answers right away; processing runs after the response.

    Answering 200 only after the raw payload is saved means a crash later never loses mail,
    and Postmark's retries are recognised by MessageID.
    """
    _check_credentials(credentials)
    body = await request.body()
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise AppError(400, "invalid_payload", "body is not JSON") from exc

    provider_id = str(payload.get("MessageID") or "") or hashlib.sha256(body).hexdigest()
    if await db.scalar(
        select(InboundEmail.id).where(
            InboundEmail.provider == "postmark", InboundEmail.provider_message_id == provider_id
        )
    ):
        return {"status": "duplicate"}

    inbound_id = uuid.uuid4()
    key = raw_key(inbound_id)
    await get_storage().put(key, body, "application/json")
    db.add(
        InboundEmail(
            id=inbound_id, provider="postmark", provider_message_id=provider_id, raw_key=key
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # The same delivery arrived twice at once; the other request owns it.
        return {"status": "duplicate"}

    background.add_task(_process, inbound_id)
    return {"status": "accepted"}


async def _process(inbound_id: uuid.UUID) -> None:
    storage = get_storage()
    async with SessionLocal() as db:
        message_id = await process_inbound(db, storage, inbound_id)
        if message_id is None:
            return
        # A missing suggestion only means the person files by hand; never lose the email over it.
        try:
            await suggest_for_message(db, storage, get_classifier(), message_id)
        except Exception:
            log.exception("could not suggest filing for message %s", message_id)
