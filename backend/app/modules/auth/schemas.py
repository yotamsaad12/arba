import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.enums import ClientType, OrgRole

# "web" keeps the refresh token in an httpOnly cookie; "mobile" gets it in the body
# so the app can keep it in secure storage.
ClientKind = Literal["web", "mobile"]


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    client_type: ClientType
    organization_name: str | None = Field(default=None, max_length=200)
    client: ClientKind = "web"

    @model_validator(mode="after")
    def _business_needs_org_name(self) -> "RegisterIn":
        if self.client_type == ClientType.business and not self.organization_name:
            raise ValueError("organization_name is required for business accounts")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    client: ClientKind = "web"


class RefreshIn(BaseModel):
    # Mobile sends the token here; web leaves it empty and relies on the cookie.
    refresh_token: str | None = None
    client: ClientKind = "web"


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_token: str | None = None


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    type: ClientType
    role: OrgRole


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    phone: str | None
    organizations: list[OrganizationOut]
