from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.db.models import RefreshSession, User
from backend.security import create_refresh_token, hash_refresh_token

REFRESH_COOKIE_PATH = "/api/v1/auth"


class RefreshSessionError(RuntimeError):
    """Raised when an opaque refresh token cannot create a new session."""


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def set_refresh_cookie(
    response: Response,
    token: str,
    settings: Settings,
) -> None:
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


async def create_refresh_session(
    session: AsyncSession,
    user_id: uuid.UUID,
    settings: Settings,
) -> str:
    token = create_refresh_token()
    session.add(
        RefreshSession(
            user_id=user_id,
            family_id=uuid.uuid4(),
            token_hash=hash_refresh_token(token),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await session.commit()
    return token


async def rotate_refresh_session(
    session: AsyncSession,
    token: str,
    settings: Settings,
) -> tuple[str, User]:
    token_hash = hash_refresh_token(token)
    stored = (
        await session.scalars(
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )
    ).one_or_none()
    if stored is None:
        raise RefreshSessionError("Unknown refresh session")

    now = datetime.now(UTC)
    if stored.revoked_at is not None:
        if stored.replaced_by_id is not None:
            await session.execute(
                update(RefreshSession)
                .where(RefreshSession.family_id == stored.family_id)
                .where(RefreshSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await session.commit()
        raise RefreshSessionError("Refresh token reuse detected")
    if _aware_utc(stored.expires_at) <= now:
        stored.revoked_at = now
        await session.commit()
        raise RefreshSessionError("Refresh session expired")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        stored.revoked_at = now
        await session.commit()
        raise RefreshSessionError("Refresh session user is inactive")

    replacement_token = create_refresh_token()
    replacement = RefreshSession(
        id=uuid.uuid4(),
        user_id=stored.user_id,
        family_id=stored.family_id,
        token_hash=hash_refresh_token(replacement_token),
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(replacement)
    stored.revoked_at = now
    stored.replaced_by_id = replacement.id
    await session.commit()
    return replacement_token, user


async def revoke_refresh_session(
    session: AsyncSession,
    token: str | None,
) -> None:
    if not token:
        return
    stored = (
        await session.scalars(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_refresh_token(token)
            )
        )
    ).one_or_none()
    if stored is None:
        return
    now = datetime.now(UTC)
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.family_id == stored.family_id)
        .where(RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.commit()


async def revoke_all_user_sessions(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> None:
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id)
        .where(RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
