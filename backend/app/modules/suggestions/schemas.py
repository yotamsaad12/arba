import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.enums import MessageKind, RequirementStatus


class SuggestionOut(BaseModel):
    id: uuid.UUID
    target: Literal["thread", "document"]
    thread_id: uuid.UUID | None
    document_id: uuid.UUID | None
    # The thread subject or the file name.
    title: str
    sender: str | None
    file_count: int
    requirement_id: uuid.UUID | None
    requirement_title: str | None
    requirement_status: RequirementStatus | None
    kind: MessageKind
    suggested_status: RequirementStatus | None
    summary: str
    reason: str
    confidence: float
    source: str
    created_at: datetime


class AcceptSuggestion(BaseModel):
    # Leave out to accept Arba's choice; send a different id (or null) to change it.
    requirement_id: uuid.UUID | None = None
    apply_status: bool = True


class AcceptResult(BaseModel):
    requirement_id: uuid.UUID
    status_applied: bool
    # Error code when the status could not change, e.g. dependencies_not_done.
    status_error: str | None
