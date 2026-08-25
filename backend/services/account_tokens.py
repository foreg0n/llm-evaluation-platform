from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AccountActionToken, User
from backend.security import (
    create_account_action_token,
    hash_account_action_token,
)

AccountTokenPurpose = Literal["verify_email", "reset_password"]
VERIFY_EMAIL: AccountTokenPurpose = "verify_email"
RESET_PASSWORD: AccountTokenPurpose = "reset_password"


class AccountTokenError(RuntimeError):
    """Raised when an account action token cannot be consumed."""


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def issue_account_token(
    session: AsyncSession,
    user_id: uuid.UUID,
    purpose: AccountTokenPurpose,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    await session.execute(
        update(AccountActionToken)
        .where(AccountActionToken.user_id == user_id)
        .where(AccountActionToken.purpose == purpose)
        .where(AccountActionToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    token = create_account_action_token()
    session.add(
        AccountActionToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_account_action_token(token),
            expires_at=now + expires_delta,
        )
    )
    await session.commit()
    return token


async def get_valid_account_token(
    session: AsyncSession,
    token: str,
    purpose: AccountTokenPurpose,
) -> tuple[AccountActionToken, User]:
    stored = (
        await session.scalars(
            select(AccountActionToken)
            .where(
                AccountActionToken.token_hash
                == hash_account_action_token(token),
                AccountActionToken.purpose == purpose,
            )
            .with_for_update()
        )
    ).one_or_none()
    now = datetime.now(UTC)
    if (
        stored is None
        or stored.consumed_at is not None
        or _aware_utc(stored.expires_at) <= now
    ):
        raise AccountTokenError("Invalid or expired account token")
    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AccountTokenError("Account token user is inactive")
    return stored, user


async def consume_user_tokens(
    session: AsyncSession,
    user_id: uuid.UUID,
    purpose: AccountTokenPurpose,
    consumed_at: datetime | None = None,
) -> None:
    await session.execute(
        update(AccountActionToken)
        .where(AccountActionToken.user_id == user_id)
        .where(AccountActionToken.purpose == purpose)
        .where(AccountActionToken.consumed_at.is_(None))
        .values(consumed_at=consumed_at or datetime.now(UTC))
    )
