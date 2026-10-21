import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.enums import MessageDirection
from app.modules.documents.schemas import DocumentOut


class ThreadSummary(BaseModel):
    id: uuid.UUID
    subject: str
    counterparty_email: str
    counterparty_name: str | None
    last_message_at: datetime
    message_count: int
    unread_count: int
    attachment_count: int
    requirement_id: uuid.UUID | None
    requirement_title: str | None
    snippet: str


class MessageOut(BaseModel):
    id: uuid.UUID
    direction: MessageDirection
    from_email: str
    from_name: str | None
    to: list[str]
    cc: list[str]
    subject: str
    text_body: str
    sent_at: datetime
    read_at: datetime | None
    attachments: list[DocumentOut]


class ThreadDetail(ThreadSummary):
    messages: list[MessageOut]


class FileThread(BaseModel):
    requirement_id: uuid.UUID | None
