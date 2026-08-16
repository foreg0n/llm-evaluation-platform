from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.db.models import User
from backend.db.session import get_db_session
from backend.schemas import TokenResponse, UserLogin, UserRead, UserRegister
from backend.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
TokenDependency = Annotated[str, Depends(oauth2_scheme)]


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: TokenDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> User:
    try:
        user_id = decode_access_token(token, settings)
    except InvalidTokenError as exc:
        raise _credentials_error() from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_error()
    return user


CurrentUserDependency = Annotated[User, Depends(get_current_user)]


async def _authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    normalized_email = email.strip().lower()
    user = (
        await session.scalars(select(User).where(User.email == normalized_email))
    ).one_or_none()
    valid_password = False
    if user is not None and user.is_active:
        valid_password = await asyncio.to_thread(
            verify_password,
            password,
            user.password_hash,
        )
    if user is None or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _token_response(user: User, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    payload: UserRegister,
    session: SessionDependency,
) -> User:
    user = User(
        email=str(payload.email),
        password_hash=await asyncio.to_thread(hash_password, payload.password),
        is_active=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    await session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    session: SessionDependency,
    settings: SettingsDependency,
) -> TokenResponse:
    user = await _authenticate_user(session, str(payload.email), payload.password)
    return _token_response(user, settings)


@router.post("/token", response_model=TokenResponse)
async def oauth2_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDependency,
    settings: SettingsDependency,
) -> TokenResponse:
    user = await _authenticate_user(session, form.username, form.password)
    return _token_response(user, settings)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: CurrentUserDependency) -> User:
    return current_user
