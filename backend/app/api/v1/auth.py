from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.errors import AppError
from app.modules.auth import service
from app.modules.auth.schemas import (
    ClientKind,
    LoginIn,
    MeOut,
    OrganizationOut,
    RefreshIn,
    RegisterIn,
    TokenOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "arba_refresh"
_COOKIE_PATH = "/api/v1/auth"


def _token_response(response: Response, access: str, refresh: str, client: ClientKind) -> TokenOut:
    expires_in = settings.access_token_minutes * 60
    if client == "mobile":
        return TokenOut(access_token=access, expires_in=expires_in, refresh_token=refresh)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )
    return TokenOut(access_token=access, expires_in=expires_in)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, db: DB, response: Response) -> TokenOut:
    user = await service.register(db, data)
    access, refresh = await service.issue_tokens(db, user)
    return _token_response(response, access, refresh, data.client)


@router.post("/login")
async def login(data: LoginIn, db: DB, response: Response) -> TokenOut:
    user = await service.authenticate(db, data.email, data.password)
    access, refresh = await service.issue_tokens(db, user)
    return _token_response(response, access, refresh, data.client)


@router.post("/refresh")
async def refresh(
    db: DB,
    response: Response,
    data: RefreshIn | None = None,
    cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenOut:
    data = data or RefreshIn()
    token = data.refresh_token or cookie
    if not token:
        raise AppError(401, "invalid_refresh_token", "no refresh token")
    _, access, new_refresh = await service.rotate_refresh_token(db, token)
    return _token_response(response, access, new_refresh, data.client)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    db: DB,
    response: Response,
    data: RefreshIn | None = None,
    cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    token = (data.refresh_token if data else None) or cookie
    if token:
        await service.revoke(db, token)
    response.delete_cookie(REFRESH_COOKIE, path=_COOKIE_PATH)


@router.get("/me")
async def me(db: DB, user: CurrentUser) -> MeOut:
    memberships = await service.memberships_of(db, user)
    return MeOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        organizations=[
            OrganizationOut(
                id=m.organization.id,
                name=m.organization.name,
                type=m.organization.type,
                role=m.role,
            )
            for m in memberships
        ],
    )
