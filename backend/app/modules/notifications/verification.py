"""Connecting a WhatsApp number: consent, then a one-time code sent to that number.

The code proves the number belongs to the person, so Arba never messages someone who didn't ask.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_token
from app.db.models import PhoneVerification, User
from app.whatsapp.client import WhatsAppSender
from app.whatsapp.phone import normalize_phone
from app.whatsapp.templates import VERIFY_CODE, WELCOME

log = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
MAX_CODES_PER_HOUR = 5


def _hash(user: User, code: str) -> str:
    return hash_token(f"{user.id}:{code}")


def _sender(sender: WhatsAppSender | None) -> WhatsAppSender:
    if sender is None:
        raise AppError(503, "whatsapp_unavailable", "WhatsApp is not configured")
    return sender


async def start(db: AsyncSession, user: User, raw_phone: str, sender: WhatsAppSender | None) -> str:
    sender = _sender(sender)
    phone = normalize_phone(raw_phone)
    if phone is None:
        raise AppError(422, "invalid_phone", "not a valid phone number")
    taken = await db.scalar(
        select(User.id).where(
            User.whatsapp_phone == phone, User.id != user.id, User.whatsapp_verified_at.is_not(None)
        )
    )
    if taken:
        raise AppError(409, "phone_taken", "this number is connected to another account")
    now = datetime.now(UTC)
    recent = await db.scalar(
        select(func.count())
        .select_from(PhoneVerification)
        .where(
            PhoneVerification.user_id == user.id,
            PhoneVerification.created_at >= now - timedelta(hours=1),
        )
    )
    if (recent or 0) >= MAX_CODES_PER_HOUR:
        raise AppError(429, "too_many_codes", "too many codes requested; try again later")

    code = f"{secrets.randbelow(10**6):06d}"
    await sender.send_template(phone, VERIFY_CODE, [code])
    db.add(
        PhoneVerification(
            user_id=user.id, phone=phone, code_hash=_hash(user, code), expires_at=now + CODE_TTL
        )
    )
    await db.commit()
    return phone


async def confirm(db: AsyncSession, user: User, code: str, sender: WhatsAppSender | None) -> str:
    now = datetime.now(UTC)
    verification = await db.scalar(
        select(PhoneVerification)
        .where(PhoneVerification.user_id == user.id, PhoneVerification.verified_at.is_(None))
        .order_by(PhoneVerification.created_at.desc())
        .limit(1)
    )
    if verification is None or verification.expires_at <= now:
        raise AppError(410, "code_expired", "the code expired; request a new one")
    if verification.attempts >= MAX_ATTEMPTS:
        raise AppError(429, "too_many_attempts", "too many wrong codes; request a new one")
    if not secrets.compare_digest(verification.code_hash, _hash(user, code.strip())):
        verification.attempts += 1
        await db.commit()
        raise AppError(422, "wrong_code", "wrong code")

    verification.verified_at = now
    user.whatsapp_phone = verification.phone
    user.whatsapp_verified_at = now
    user.whatsapp_opted_out_at = None
    user.notify_whatsapp = True
    await db.commit()

    if sender is not None:
        first_name = user.name.split()[0] if user.name.strip() else ""
        try:
            await sender.send_template(verification.phone, WELCOME, [first_name])
        except Exception:  # noqa: BLE001 - connected either way; the welcome is a courtesy
            log.exception("welcome message failed for %s", user.id)
    return verification.phone


async def disconnect(db: AsyncSession, user: User) -> None:
    user.whatsapp_phone = None
    user.whatsapp_verified_at = None
    user.whatsapp_last_inbound_at = None
    await db.commit()
