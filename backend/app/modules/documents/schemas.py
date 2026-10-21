import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import DocumentSource


class DocumentOut(BaseModel):
    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    source: DocumentSource
    requirement_id: uuid.UUID | None
    message_id: uuid.UUID | None
    created_at: datetime
    uploaded_by_name: str | None
    # Short-lived; refetch the list rather than storing it.
    download_url: str


class UploadRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=150)
    size_bytes: int = Field(gt=0)
    requirement_id: uuid.UUID | None = None


class UploadTarget(BaseModel):
    url: str
    method: str
    headers: dict[str, str]


class UploadStarted(BaseModel):
    document_id: uuid.UUID
    upload: UploadTarget


class FileDocument(BaseModel):
    requirement_id: uuid.UUID | None
