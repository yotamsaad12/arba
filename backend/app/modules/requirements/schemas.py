import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.core.enums import AuthorityType, Form4Track


class ImportedItemOut(BaseModel):
    id: uuid.UUID
    number: str | None
    title: str
    track: Form4Track
    authority_type: AuthorityType
    standard: str | None
    appendix: str | None
    notes: str | None
    due_date: date | None
    # The authority's list marks it as not needed ("אין צורך").
    not_needed: bool
    # Arba's proposal: the existing item this is (null: a new item).
    match_requirement_id: uuid.UUID | None
    match_title: str | None
    # proposed, added, merged, skipped
    status: str
    requirement_id: uuid.UUID | None


class ImportOut(BaseModel):
    id: uuid.UUID
    file_name: str
    track: Form4Track | None
    source: str
    applied_at: datetime | None
    items: list[ImportedItemOut]


class ImportDecision(BaseModel):
    item_id: uuid.UUID
    action: Literal["merge", "add", "skip"]
    # Merge into a different item than the one Arba proposed.
    requirement_id: uuid.UUID | None = None


class ApplyImport(BaseModel):
    # Leave out to apply Arba's proposals as they are.
    decisions: list[ImportDecision] | None = None


class ImportFromDocument(BaseModel):
    document_id: uuid.UUID
