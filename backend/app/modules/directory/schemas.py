import uuid
from datetime import date

from pydantic import BaseModel

from app.core.enums import AuthorityType, Channel, ContactSource


class LocalityOut(BaseModel):
    code: int
    name: str
    municipality_code: int | None
    municipality: str | None
    committee_code: str | None
    committee: str | None
    # "planning_map" (official) or "assumed".
    committee_source: str | None


class ContactOut(BaseModel):
    id: uuid.UUID
    purpose: str
    channel: Channel
    email: str | None
    phone: str | None
    url: str | None
    source: ContactSource
    source_url: str | None
    verified_at: date | None


class AuthorityOut(BaseModel):
    id: uuid.UUID
    type: AuthorityType
    name: str
    website: str | None
    permit_search_url: str | None
    national: bool
    contacts: list[ContactOut]
