import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.enums import AuthorityType, CheckVerdict, RequestStatus


class ContactIn(BaseModel):
    role: AuthorityType
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def _reachable(self) -> "ContactIn":
        if not self.email and not self.phone:
            raise ValueError("an email address or a phone number is needed")
        return self


class TeamMemberOut(BaseModel):
    id: uuid.UUID
    role: AuthorityType
    name: str
    email: str | None
    phone: str | None


class RequestCreate(BaseModel):
    requirement_id: uuid.UUID
    # An existing team member, or a new one (saved to the team).
    contact_id: uuid.UUID | None = None
    contact: ContactIn | None = None
    documents: list[str] = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _one_contact(self) -> "RequestCreate":
        if (self.contact_id is None) == (self.contact is None):
            raise ValueError("give either contact_id or contact")
        return self


class FileOut(BaseModel):
    id: uuid.UUID
    file_name: str
    created_at: datetime
    check_status: CheckVerdict | None


class RequestOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    requirement_title: str
    contact: TeamMemberOut
    documents: list[str]
    note: str | None
    status: RequestStatus
    link: str
    sent_count: int
    last_sent_at: datetime | None
    fulfilled_at: datetime | None
    created_at: datetime
    files: list[FileOut]
    # How the request went out: email, whatsapp (empty when neither could be sent).
    sent_by: list[str] = []


# --- The professional's page (no account) ---------------------------------------------


class PublicRequestOut(BaseModel):
    project_name: str
    place: str
    requested_by: str
    contact_name: str
    role: AuthorityType
    requirement_title: str
    documents: list[str]
    note: str | None
    status: RequestStatus
    expires_at: datetime
    files: list[FileOut]
    max_upload_mb: int


class PublicUpload(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=150)
    size_bytes: int = Field(gt=0)
