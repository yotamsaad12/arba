import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ClientType, OrgRole
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.db.models import Membership, Organization, RefreshToken, User
from app.modules.auth.schemas import RegisterIn

# Two tabs refreshing at once both send the same cookie. Reuse inside this window is not theft.
REFRESH_REUSE_GRACE = timedelta(seconds=10)


def _invalid_credentials() -> AppError:
    return AppError(401, "invalid_credentials", "wrong email or password")


async def register(db: AsyncSession, data: RegisterIn) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise AppError(409, "email_taken", "email already registered")
    user = User(
        id=uuid.uuid4(),
        name=data.name,
        email=email,
        phone=data.phone,
        password_hash=hash_password(data.password),
    )
    org = Organization(
        id=uuid.uuid4(),
        name=data.organization_name if data.client_type == ClientType.business else data.name,
        type=data.client_type,
    )
    db.add_all([user, org])
    await db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=OrgRole.owner))
    await db.commit()
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise _invalid_credentials()
    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    """Returns (access token, refresh token)."""
    refresh, refresh_hash = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    await db.commit()
    return create_access_token(user.id), refresh


async def rotate_refresh_token(db: AsyncSession, token: str) -> tuple[User, str, str]:
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
    )
    now = datetime.now(UTC)
    if stored is None or stored.expires_at <= now or stored.revoked_at is not None:
        raise AppError(401, "invalid_refresh_token", "refresh token is invalid or expired")
    if stored.rotated_at is None:
        stored.rotated_at = now
    elif now - stored.rotated_at > REFRESH_REUSE_GRACE:
        # A rotated token was used again: assume it leaked and end every session of this user.
        await revoke_all(db, stored.user_id)
        raise AppError(401, "invalid_refresh_token", "refresh token is invalid or expired")
    # Otherwise a second tab refreshed with the same cookie a moment ago; let it through.
    user = await db.get(User, stored.user_id)
    if user is None:
        raise AppError(401, "invalid_refresh_token", "refresh token is invalid or expired")
    access, refresh = await issue_tokens(db, user)
    return user, access, refresh


async def revoke(db: AsyncSession, token: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def revoke_all(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def memberships_of(db: AsyncSession, user: User) -> list[Membership]:
    return list(await db.scalars(select(Membership).where(Membership.user_id == user.id)))
