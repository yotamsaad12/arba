import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import AuthorityType, ConditionStatus, ConditionTiming, PermitStatus
from app.modules.directory.schemas import LocalityOut


class PermitFields(BaseModel):
    is_permit: bool = True
    permit_number: str | None = None
    request_number: str | None = None
    committee: str | None = None
    locality: str | None = None
    address: str | None = None
    gush: str | None = None
    helka: str | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    applicants: list[str] = Field(default_factory=list)
    description: str | None = None


class PermitExtraction(BaseModel):
    fields: PermitFields
    source: Literal["claude", "rules"]
    # Best guess for the project's locality, from the permit's locality or committee.
    locality: LocalityOut | None


class PermitCheck(BaseModel):
    check: Literal["document", "number", "validity", "committee", "location"]
    # None: couldn't be checked (e.g. no committee written on the permit).
    ok: bool | None
    message: str


class PermitOut(BaseModel):
    status: PermitStatus
    number: str | None
    request_number: str | None
    issue_date: date | None
    valid_until: date | None
    committee_on_permit: str | None
    official_committee: str | None
    checks: list[PermitCheck]
    confirmed_at: datetime | None
    # Where to look the permit up at the committee, when known.
    search_url: str | None
    committee_website: str | None
    # The requirement the permit file is filed under.
    requirement_id: uuid.UUID | None


class PermitUpdate(BaseModel):
    permit_number: str | None = None
    permit_request_number: str | None = None
    permit_issue_date: date | None = None
    permit_valid_until: date | None = None
    permit_committee: str | None = None


class ConditionOut(BaseModel):
    id: uuid.UUID
    number: str | None
    text: str
    title: str
    timing: ConditionTiming
    stage: str
    authority_type: AuthorityType
    documents: list[str]
    status: ConditionStatus
    # Arba's proposal: add to this existing step (null: a new step).
    match_requirement_id: uuid.UUID | None
    # Where it ended up, once accepted.
    requirement_id: uuid.UUID | None
    # The title of the step it was matched to or ended up in.
    requirement_title: str | None
    source: str


class ConditionsOut(BaseModel):
    # null (no permit file yet), reading, ready, failed.
    status: str | None
    conditions: list[ConditionOut]


class AcceptCondition(BaseModel):
    # Make it a step of its own even though Arba proposed an existing one.
    as_new: bool = False
