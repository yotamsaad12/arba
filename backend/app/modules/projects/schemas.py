import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import (
    AuthorityType,
    Channel,
    ClientType,
    PermitStatus,
    ProjectRole,
    ProjectStatus,
    RequirementOrigin,
    RequirementStatus,
)
from app.modules.permits.schemas import PermitOut


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    template_id: uuid.UUID
    # Official locality (from /directory/localities). Sets the municipality and committee.
    locality_code: int | None = None
    # Free text, only when no locality is chosen.
    municipality: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    floors: int = Field(default=1, ge=1, le=60)
    gush: str | None = Field(default=None, max_length=32)
    helka: str | None = Field(default=None, max_length=32)
    permit_number: str | None = Field(default=None, max_length=64)
    permit_request_number: str | None = Field(default=None, max_length=64)
    permit_issue_date: date | None = None
    permit_valid_until: date | None = None
    permit_committee: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _needs_a_place(self) -> "ProjectCreate":
        if self.locality_code is None and not self.municipality:
            raise ValueError("choose a locality or enter a municipality")
        return self


class Stage(BaseModel):
    key: str
    title: str
    description: str | None = None


class Progress(BaseModel):
    done: int
    total: int


class StageProgress(BaseModel):
    stage: str
    # Set for requirements that repeat per floor (the skeleton), one entry per floor.
    floor: int | None
    done: int
    total: int
    # Marked not applicable. Counted in `done`; lets the client hide e.g. green-building visuals.
    skipped: int


class BuildState(BaseModel):
    """Where construction stands, for progress visuals."""

    progress: Progress
    stages: list[StageProgress]
    # Stage and floor of the next open step on the critical path: where work is happening now.
    focus_stage: str | None
    focus_floor: int | None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str | None
    municipality: str
    building_type: str
    client_type: ClientType
    floors: int
    gush: str | None
    helka: str | None
    permit_number: str | None
    permit_valid_until: date | None
    inbox_address: str
    status: ProjectStatus
    created_at: datetime
    locality_code: int | None
    municipality_code: int | None
    permit_status: PermitStatus
    role: ProjectRole
    build: BuildState


class InboxCounts(BaseModel):
    unread: int
    # Conversations not filed under a requirement yet.
    unfiled: int
    # Filing proposals waiting for a person's approval (mail and documents).
    pending_suggestions: int


class ProjectDetail(ProjectOut):
    stages: list[Stage]
    permit: PermitOut
    inbox: InboxCounts


class RequirementOut(BaseModel):
    id: uuid.UUID
    stage: str
    title: str
    description: str | None
    authority_type: AuthorityType
    channel: Channel
    estimated_days: int
    floor: int | None
    required_documents: list[str]
    optional: bool
    is_form4_gate: bool
    order: int
    status: RequirementStatus
    status_changed_at: datetime | None
    completed_at: datetime | None
    depends_on: list[uuid.UUID]
    # Dependencies not done yet. Non-empty on a started requirement means something regressed.
    blocked_by: list[uuid.UUID]
    on_critical_path: bool
    document_count: int
    # template, permit_condition (from the permit) or city_list (the authority's own list).
    origin: RequirementOrigin
    # What Arba's document checks found ("⛔ file: issue"), most serious first.
    check_issues: list[str] = []


class RequirementList(BaseModel):
    stages: list[Stage]
    requirements: list[RequirementOut]


class CriticalPath(BaseModel):
    requirement_ids: list[uuid.UUID]
    remaining_days: int


class NextSteps(BaseModel):
    ready: list[RequirementOut]
    active: list[RequirementOut]
    waiting: list[RequirementOut]
    blocked: list[RequirementOut]
    critical_path: CriticalPath
    progress: Progress


class StatusUpdate(BaseModel):
    status: RequirementStatus


def stages_of(project: Any) -> list[Stage]:
    return [Stage(**s) for s in (project.template.stages if project.template else [])]
