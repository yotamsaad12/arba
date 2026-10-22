import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import DeliveryChannel, DeliveryStatus, NotificationKind, Urgency


class WhatsAppStatus(BaseModel):
    connected: bool
    phone: str | None
    opted_out: bool


class SettingsOut(BaseModel):
    notify_email: bool
    notify_whatsapp: bool
    quiet_nights: bool
    quiet_shabbat: bool
    digest_hour: int
    whatsapp: WhatsAppStatus
    whatsapp_available: bool
    # Dev only: messages go to the /dev/whatsapp simulator instead of real WhatsApp.
    whatsapp_simulator: bool


class SettingsUpdate(BaseModel):
    notify_email: bool | None = None
    notify_whatsapp: bool | None = None
    quiet_nights: bool | None = None
    quiet_shabbat: bool | None = None
    digest_hour: int | None = Field(default=None, ge=5, le=12)


class StartWhatsApp(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    # The person agreed to receive WhatsApp messages from Arba (Meta requires opt-in).
    consent: Literal[True]


class ConfirmWhatsApp(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class CodeSent(BaseModel):
    phone: str


class DeliveryOut(BaseModel):
    channel: DeliveryChannel
    status: DeliveryStatus
    # Why it failed or was skipped, for the test button in Settings.
    error: str | None = None


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: NotificationKind
    urgency: Urgency
    title: str
    body: str
    action_path: str | None
    project_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None
    deliveries: list[DeliveryOut]


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


class SimMessage(BaseModel):
    id: uuid.UUID
    direction: Literal["in", "out"]
    text: str
    buttons: list[dict[str, str]]
    created_at: datetime


class SimChat(BaseModel):
    phone: str
    name: str | None
    last_text: str
    last_at: datetime


class SimSend(BaseModel):
    text: str | None = None
    button_id: str | None = None
    button_title: str | None = None
