"""Notifications: who hears about what, on which channel, and when.

Every notification shows in the app. Urgent ones (and the morning summary) are also pushed by
email and WhatsApp, per the person's settings, outside their quiet hours. Deliveries are rows in
the database that the worker sends when due, so nothing is lost if a channel is down.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    PROJECT_ROLE_RANK,
    DeliveryChannel,
    DeliveryStatus,
    NotificationKind,
    ProjectRole,
    Urgency,
)
from app.db.models import Delivery, Notification, ProjectMember, User
from app.email import outgoing
from app.modules.notifications.quiet import quiet_until
from app.whatsapp.client import WhatsAppSender, get_whatsapp
from app.whatsapp.templates import BY_NAME

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BATCH_SIZE = 50
SESSION_WINDOW = timedelta(hours=24)


@dataclass
class WhatsAppContent:
    template: str
    params: list[str]
    # (payload, title) per quick-reply button, in the template's button order.
    buttons: list[tuple[str, str]] = field(default_factory=list)
    # Used instead of the template inside the 24h window, where free-form text is allowed.
    session_text: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "template": self.template,
            "params": self.params,
            "buttons": [list(b) for b in self.buttons],
            "session_text": self.session_text,
        }


async def members(
    db: AsyncSession, project_id: uuid.UUID, min_role: ProjectRole = ProjectRole.viewer
) -> list[User]:
    rows = await db.execute(
        select(User, ProjectMember.role)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
    )
    return [u for u, role in rows if PROJECT_ROLE_RANK[role] >= PROJECT_ROLE_RANK[min_role]]


def pushes(notification: Notification) -> bool:
    return (
        notification.urgency == Urgency.urgent or notification.kind == NotificationKind.daily_digest
    )


async def notify(
    db: AsyncSession,
    users: list[User],
    *,
    kind: NotificationKind,
    urgency: Urgency,
    title: str,
    body: str,
    project_id: uuid.UUID | None = None,
    action_path: str | None = None,
    suggestion_id: uuid.UUID | None = None,
    whatsapp: WhatsAppContent | None = None,
    dedupe_key: str | None = None,
    now: datetime | None = None,
    ignore_quiet_hours: bool = False,
) -> list[Notification]:
    """Creates one notification per person and queues its pushes. Commits."""
    now = now or datetime.now(UTC)
    created = []
    for user in users:
        # Same dedupe key for the same person: already told, do nothing.
        result = await db.execute(
            insert(Notification)
            .values(
                id=uuid.uuid4(),
                user_id=user.id,
                project_id=project_id,
                kind=kind,
                urgency=urgency,
                title=title,
                body=body,
                action_path=action_path,
                suggestion_id=suggestion_id,
                whatsapp=whatsapp.as_json() if whatsapp else None,
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
            .returning(Notification)
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            continue
        created.append(notification)
        if pushes(notification):
            due = now if ignore_quiet_hours else quiet_until(user, now) or now
            channels = [DeliveryChannel.email]
            if whatsapp is not None:
                channels.append(DeliveryChannel.whatsapp)
            for channel in channels:
                db.add(Delivery(notification_id=notification.id, channel=channel, due_at=due))
    await db.commit()
    # Without a worker (serverless), what is due now goes out now; the cron sends the rest.
    if created and not settings.run_worker_in_api and settings.env != "test":
        await deliver_due(db, now)
    return created


async def resolve_for_suggestion(db: AsyncSession, suggestion_id: uuid.UUID) -> None:
    """Once someone decided, the question is answered for everyone: mark read, stop pushes."""
    now = datetime.now(UTC)
    await db.execute(
        update(Notification)
        .where(Notification.suggestion_id == suggestion_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    pending = select(Notification.id).where(Notification.suggestion_id == suggestion_id)
    await db.execute(
        update(Delivery)
        .where(Delivery.notification_id.in_(pending), Delivery.status == DeliveryStatus.queued)
        .values(status=DeliveryStatus.skipped, error="resolved before sending")
    )


async def deliver_due(
    db: AsyncSession, now: datetime | None = None, limit: int = BATCH_SIZE
) -> int:
    """Sends queued deliveries that are due. Safe to run in several workers at once."""
    now = now or datetime.now(UTC)
    rows = await db.execute(
        select(Delivery, Notification, User)
        .join(Notification, Notification.id == Delivery.notification_id)
        .join(User, User.id == Notification.user_id)
        .where(Delivery.status == DeliveryStatus.queued, Delivery.due_at <= now)
        .order_by(Delivery.due_at)
        .limit(limit)
        .with_for_update(of=Delivery, skip_locked=True)
    )
    batch = list(rows)
    whatsapp = get_whatsapp()
    for delivery, notification, user in batch:
        try:
            await _send(delivery, notification, user, whatsapp, now)
        except Exception as exc:  # noqa: BLE001 - record and retry later
            delivery.attempts += 1
            delivery.error = f"{type(exc).__name__}: {exc}"[:1000]
            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = DeliveryStatus.failed
            else:
                delivery.due_at = now + timedelta(minutes=2**delivery.attempts)
            log.warning("delivery %s failed: %s", delivery.id, delivery.error)
    await db.commit()
    return len(batch)


async def _send(
    delivery: Delivery,
    notification: Notification,
    user: User,
    whatsapp: WhatsAppSender | None,
    now: datetime,
) -> None:
    link = f"{settings.app_url}{notification.action_path or '/'}"
    if delivery.channel == DeliveryChannel.email:
        if not user.notify_email:
            delivery.status = DeliveryStatus.skipped
            delivery.error = "email notifications are off"
            return
        message = outgoing.build(user.email, notification.title, notification.body, link)
        if not await outgoing.send(message):
            delivery.status = DeliveryStatus.skipped
            delivery.error = "recipient not in ARBA_EMAIL_ALLOWED_RECIPIENTS"
            return
    else:
        content = notification.whatsapp or {}
        if whatsapp is None or not user.notify_whatsapp or not user.whatsapp_active or not content:
            delivery.status = DeliveryStatus.skipped
            delivery.error = "WhatsApp is not connected or is off"
            return
        to = user.whatsapp_phone or ""
        buttons = [(str(b[0]), str(b[1])) for b in content.get("buttons") or []]
        in_session = bool(
            user.whatsapp_last_inbound_at and now - user.whatsapp_last_inbound_at < SESSION_WINDOW
        )
        if in_session and content.get("session_text"):
            text = str(content["session_text"])
            delivery.provider_message_id = (
                await whatsapp.send_buttons(to, text, buttons)
                if buttons
                else await whatsapp.send_text(to, f"{text}\n{link}")
            )
        else:
            template = BY_NAME[str(content["template"])]
            delivery.provider_message_id = await whatsapp.send_template(
                to, template, [str(p) for p in content["params"]], [b[0] for b in buttons]
            )
    delivery.status = DeliveryStatus.sent
    delivery.sent_at = now
    delivery.error = None


STATUS_ORDER = {"sent": 1, "delivered": 2, "read": 3}


async def record_status(db: AsyncSession, message_id: str, status: str, error: str | None) -> None:
    delivery = await db.scalar(select(Delivery).where(Delivery.provider_message_id == message_id))
    if delivery is None:
        return
    if status == "failed":
        delivery.status = DeliveryStatus.failed
        delivery.error = error
    elif STATUS_ORDER.get(status, 0) > STATUS_ORDER.get(delivery.status.value, 0):
        delivery.status = DeliveryStatus(status)
