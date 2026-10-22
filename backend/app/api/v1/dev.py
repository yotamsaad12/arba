"""Development tools. Mounted only in dev and test, and only with the WhatsApp simulator."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.deps import DB, CurrentUser
from app.core.errors import AppError
from app.db.models import SimulatedWhatsApp, User
from app.modules.notifications.schemas import SimChat, SimMessage, SimSend
from app.modules.notifications.whatsapp_actions import handle
from app.whatsapp.client import SimulatorSender
from app.whatsapp.phone import normalize_phone
from app.whatsapp.webhook import message_payload, parse

router = APIRouter(prefix="/dev/whatsapp", tags=["dev"])


def _phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if phone is None:
        raise AppError(422, "invalid_phone", "not a valid phone number")
    return phone


@router.get("/chats")
async def chats(db: DB, _: CurrentUser) -> list[SimChat]:
    latest = (
        select(SimulatedWhatsApp.phone, func.max(SimulatedWhatsApp.created_at).label("at"))
        .group_by(SimulatedWhatsApp.phone)
        .subquery()
    )
    rows = await db.execute(
        select(SimulatedWhatsApp, User.name)
        .join(
            latest,
            (latest.c.phone == SimulatedWhatsApp.phone)
            & (latest.c.at == SimulatedWhatsApp.created_at),
        )
        .outerjoin(User, User.whatsapp_phone == SimulatedWhatsApp.phone)
        .order_by(SimulatedWhatsApp.created_at.desc())
    )
    return [
        SimChat(phone=m.phone, name=name, last_text=m.text[:120], last_at=m.created_at)
        for m, name in rows
    ]


@router.get("/chats/{phone}")
async def messages(phone: str, db: DB, _: CurrentUser) -> list[SimMessage]:
    rows = await db.scalars(
        select(SimulatedWhatsApp)
        .where(SimulatedWhatsApp.phone == _phone(phone))
        .order_by(SimulatedWhatsApp.created_at)
    )
    return [
        SimMessage(
            id=m.id,
            direction="in" if m.direction == "in" else "out",
            text=m.text,
            buttons=m.buttons,
            created_at=m.created_at,
        )
        for m in rows
    ]


@router.post("/chats/{phone}/send")
async def send(phone: str, data: SimSend, db: DB, user: CurrentUser) -> list[SimMessage]:
    """Plays the person's side: a typed message or a button press, handled exactly like
    Meta's webhook would deliver it."""
    number = _phone(phone)
    message_id = f"sim.in.{uuid.uuid4().hex}"
    text = data.button_title or data.text or ""
    db.add(
        SimulatedWhatsApp(
            phone=number, direction="in", text=text, buttons=[], provider_message_id=message_id
        )
    )
    await db.commit()
    payload = message_payload(
        number, message_id, button=data.button_id, title=data.button_title or "", text=text
    )
    await handle(db, parse(payload), SimulatorSender(), datetime.now(UTC))
    return await messages(number, db, user)
