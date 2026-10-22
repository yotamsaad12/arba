"""What a filing classifier receives and returns, independent of the engine."""

import uuid
from dataclasses import dataclass, field
from typing import Literal

from app.core.enums import AuthorityType, MessageKind, RequirementStatus

# Statuses a suggestion may propose. "blocked"/"ready" are automatic; "not_applicable" is a
# decision only a person makes.
SuggestableStatus = Literal["done", "needs_fix", "waiting_for_authority", "in_progress"]


@dataclass
class Attachment:
    name: str
    content_type: str
    data: bytes | None = None


@dataclass
class Item:
    """An incoming email or an uploaded document to be filed."""

    source: Literal["email", "document"]
    subject: str
    text: str = ""
    sender_email: str | None = None
    sender_name: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    # The requirement its thread is already filed under, if any.
    current_requirement_id: uuid.UUID | None = None


@dataclass
class RequirementInfo:
    id: uuid.UUID
    title: str
    stage_title: str
    authority_type: AuthorityType
    status: RequirementStatus
    required_documents: list[str]
    order: int


@dataclass
class Decision:
    requirement_id: uuid.UUID | None
    kind: MessageKind
    suggested_status: SuggestableStatus | None
    summary: str
    reason: str
    confidence: float
    source: Literal["claude", "rules"]
    # Requests for information and rejections: what the authority asks for.
    missing_documents: list[str] = field(default_factory=list)
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


STATUS_FOR_KIND: dict[MessageKind, SuggestableStatus | None] = {
    MessageKind.approval: "done",
    MessageKind.rejection: "needs_fix",
    MessageKind.request_for_info: "needs_fix",
    MessageKind.info: None,
    MessageKind.other: None,
}
