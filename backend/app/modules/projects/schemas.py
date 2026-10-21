import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AuthorityType,
    Channel,
    ClientType,
    ProjectRole,
    ProjectStatus,
    RequirementStatus,
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    template_id: uuid.UUID
    municipality: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    floors: int = Field(default=1, ge=1, le=60)
    gush: str | None = Field(default=None, max_length=32)
    helka: str | None = Field(default=None, max_length=32)
    permit_number: str | None = Field(default=None, max_length=64)
    permit_valid_until: date | None = None


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
    role: ProjectRole
    build: BuildState


class InboxCounts(BaseModel):
    unread: int
    # Conversations not filed under a requirement yet.
    unfiled: int


class ProjectDetail(ProjectOut):
    stages: list[Stage]
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
