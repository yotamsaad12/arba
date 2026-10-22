import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.enums import MailboxProvider, RequirementStatus, ScanStatus


class MailboxConnect(BaseModel):
    provider: MailboxProvider | None
    # Gmail: open this to grant access. Simulator: null, start the scan directly.
    url: str | None


class ScanOut(BaseModel):
    id: uuid.UUID
    provider: MailboxProvider
    account_email: str
    status: ScanStatus
    query: str
    messages_found: int
    messages_imported: int
    files_imported: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class CatchUp(BaseModel):
    # The stage the project is in now; every required step before it is marked done.
    stage: str


class CatchUpResult(BaseModel):
    marked_done: int


class ReportItem(BaseModel):
    requirement_id: uuid.UUID
    title: str
    stage: str
    status: RequirementStatus
    required_documents: list[str]
    documents: int
    # Filing suggestions waiting for approval that point at this requirement.
    pending: int


class CatchUpReport(BaseModel):
    # Requirements with documents or suggestions waiting for them.
    found: list[ReportItem]
    # Marked done (or under way), with documents to keep for Form 4 but none in Arba yet.
    missing: list[ReportItem]
    pending_suggestions: int
    # Suggestions Arba couldn't place: the person decides.
    unsure: int
    scan: ScanOut | None
    state: Literal["empty", "scanning", "ready"]
