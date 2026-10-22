import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.enums import NotificationKind, Urgency
from app.core.errors import not_found
from app.db.models import Delivery, Notification, User
from app.modules.notifications import verification
from app.modules.notifications.schemas import (
    CodeSent,
    ConfirmWhatsApp,
    DeliveryOut,
    NotificationList,
    NotificationOut,
    SettingsOut,
    SettingsUpdate,
    StartWhatsApp,
    WhatsAppStatus,
)
from app.modules.notifications.service import WhatsAppContent, deliver_due, notify
from app.whatsapp.client import get_whatsapp
from app.whatsapp.phone import mask_phone

router = APIRouter(prefix="/me", tags=["me"])


def _settings(user: User) -> SettingsOut:
    return SettingsOut(
        notify_email=user.notify_email,
        notify_whatsapp=user.notify_whatsapp,
        quiet_nights=user.quiet_nights,
        quiet_shabbat=user.quiet_shabbat,
        digest_hour=user.digest_hour,
        whatsapp=WhatsAppStatus(
            connected=bool(user.whatsapp_phone and user.whatsapp_verified_at),
            phone=mask_phone(user.whatsapp_phone) if user.whatsapp_phone else None,
            opted_out=user.whatsapp_opted_out_at is not None,
        ),
        whatsapp_available=settings.whatsapp_provider != "disabled",
        whatsapp_simulator=settings.whatsapp_provider == "simulator",
    )


@router.get("/settings")
async def get_settings(user: CurrentUser) -> SettingsOut:
    return _settings(user)


@router.patch("/settings")
async def update_settings(data: SettingsUpdate, db: DB, user: CurrentUser) -> SettingsOut:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    return _settings(user)


@router.post("/whatsapp/start")
async def start_whatsapp(data: StartWhatsApp, db: DB, user: CurrentUser) -> CodeSent:
    """Sends a 6-digit code to the number on WhatsApp."""
    phone = await verification.start(db, user, data.phone, get_whatsapp())
    return CodeSent(phone=mask_phone(phone))


@router.post("/whatsapp/confirm")
async def confirm_whatsapp(data: ConfirmWhatsApp, db: DB, user: CurrentUser) -> SettingsOut:
    await verification.confirm(db, user, data.code, get_whatsapp())
    return _settings(user)


@router.delete("/whatsapp", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_whatsapp(db: DB, user: CurrentUser) -> None:
    await verification.disconnect(db, user)


@router.get("/notifications")
async def list_notifications(db: DB, user: CurrentUser, limit: int = 30) -> NotificationList:
    items = list(
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(min(limit, 100))
        )
    )
    deliveries: dict[uuid.UUID, list[DeliveryOut]] = {}
    for d in await db.scalars(
        select(Delivery).where(Delivery.notification_id.in_([n.id for n in items]))
    ):
        deliveries.setdefault(d.notification_id, []).append(
            DeliveryOut(channel=d.channel, status=d.status)
        )
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return NotificationList(
        unread=unread or 0,
        items=[
            NotificationOut(
                id=n.id,
                kind=n.kind,
                urgency=n.urgency,
                title=n.title,
                body=n.body,
                action_path=n.action_path,
                project_id=n.project_id,
                created_at=n.created_at,
                read_at=n.read_at,
                deliveries=deliveries.get(n.id, []),
            )
            for n in items
        ],
    )


@router.post("/notifications/test")
async def send_test(db: DB, user: CurrentUser) -> list[DeliveryOut]:
    """Sends a test notification now, on every channel the person has on, ignoring quiet hours."""
    first_name = user.name.split()[0] if user.name.strip() else ""
    [notification] = await notify(
        db,
        [user],
        kind=NotificationKind.test,
        urgency=Urgency.urgent,
        title="בדיקה מ-Arba ✅",
        body="אם ההודעה הזו הגיעה אליך, ההתראות עובדות. מעכשיו Arba תעדכן אותך כאן.",
        action_path="/settings",
        whatsapp=WhatsAppContent(
            template="arba_welcome",
            params=[first_name],
            session_text="בדיקה מ-Arba ✅ ההתראות ב-WhatsApp עובדות.",
        ),
        ignore_quiet_hours=True,
    )
    await deliver_due(db)
    rows = await db.scalars(select(Delivery).where(Delivery.notification_id == notification.id))
    return [DeliveryOut(channel=d.channel, status=d.status, error=d.error) for d in rows]


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(notification_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise not_found("notification")
    notification.read_at = notification.read_at or datetime.now(UTC)
    await db.commit()


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(db: DB, user: CurrentUser) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
