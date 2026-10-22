import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import Channel, DraftKind, DraftStatus


class AttachmentOut(BaseModel):
    id: uuid.UUID
    file_name: str


class DraftOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    requirement_title: str
    kind: DraftKind
    # email: Arba sends it. portal / in_person: the person submits the text themselves.
    channel: Channel
    to_email: str | None
    to_name: str | None
    portal_url: str | None
    phone: str | None
    # Where the address came from: thread, official_site, learned, user, none.
    recipient_source: str | None
    subject: str
    body: str
    attachments: list[AttachmentOut]
    # Documents the body will likely want that the project doesn't have yet.
    missing_documents: list[str]
    status: DraftStatus
    source: str
    created_at: datetime
    sent_at: datetime | None


class DraftUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    to_email: EmailStr | None = None
    attachment_ids: list[uuid.UUID] | None = None


class NewDraft(BaseModel):
    kind: DraftKind = DraftKind.request
