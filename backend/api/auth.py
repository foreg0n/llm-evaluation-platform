from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.db.models import User
from backend.db.session import get_db_session
from backend.schemas import (
    AccountEmailRequest,
    AccountTokenRequest,
    MessageResponse,
    PasswordResetConfirm,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from backend.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.services.auth_rate_limit import (
    AuthRateLimiterProtocol,
    get_auth_rate_limiter,
)
from backend.services.auth_sessions import (
    RefreshSessionError,
    clear_refresh_cookie,
    create_refresh_session,
    revoke_all_user_sessions,
    revoke_refresh_session,
    rotate_refresh_session,
    set_refresh_cookie,
)
from backend.services.account_tokens import (
    AccountTokenError,
    RESET_PASSWORD,
    VERIFY_EMAIL,
    consume_user_tokens,
    get_valid_account_token,
    issue_account_token,
)
from backend.services.email_delivery import (
    EmailSenderProtocol,
    get_email_sender,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
logger = logging.getLogger("backend.auth")

SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
TokenDependency = Annotated[str, Depends(oauth2_scheme)]
RateLimiterDependency = Annotated[
    AuthRateLimiterProtocol,
    Depends(get_auth_rate_limiter),
]
EmailSenderDependency = Annotated[
    EmailSenderProtocol,
    Depends(get_email_sender),
]

EMAIL_VERIFICATION_REQUESTED = (
    "If the account exists and needs verification, an email has been sent."
)
PASSWORD_RESET_REQUESTED = (
    "If the account exists, password reset instructions have been sent."
)


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _refresh_credentials_error(
    settings: Settings,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    clear_refresh_cookie(response, settings)
    return response


def _rate_limit_identifier(
    request: Request,
    scope: str,
    account: str = "",
) -> str:
    client_host = request.client.host if request.client is not None else "unknown"
    raw = f"{scope}|{client_host}|{account.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _enforce_rate_limit(
    limiter: AuthRateLimiterProtocol,
    identifier: str,
) -> None:
    retry_after = await limiter.hit(identifier)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
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
    settings: Settings,
) -> User:
    normalized_email = email.strip().lower()
    user = (
        await session.scalars(select(User).where(User.email == normalized_email))
    ).one_or_none()
    encoded_hash = (
        user.password_hash
        if user is not None and user.is_active
        else DUMMY_PASSWORD_HASH
    )
    valid_password = await asyncio.to_thread(
        verify_password,
        password,
        encoded_hash,
    )
    if user is None or not user.is_active or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if settings.require_email_verification and user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return user


async def _deliver_account_email(
    sender: EmailSenderProtocol,
    purpose: str,
    recipient: str,
    token: str,
) -> None:
    try:
        if purpose == VERIFY_EMAIL:
            await sender.send_email_verification(recipient, token)
        else:
            await sender.send_password_reset(recipient, token)
    except Exception:
        logger.exception(
            "account_email_delivery_failed",
            extra={"event": "account_email_delivery_failed"},
        )


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
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    settings: SettingsDependency,
    limiter: RateLimiterDependency,
    email_sender: EmailSenderDependency,
) -> User:
    await _enforce_rate_limit(
        limiter,
        _rate_limit_identifier(request, "register", str(payload.email)),
    )
    user = User(
        email=str(payload.email),
        password_hash=await asyncio.to_thread(hash_password, payload.password),
        is_active=True,
        email_verified_at=None,
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
    verification_token = await issue_account_token(
        session,
        user.id,
        VERIFY_EMAIL,
        timedelta(hours=settings.email_verification_expire_hours),
    )
    background_tasks.add_task(
        _deliver_account_email,
        email_sender,
        VERIFY_EMAIL,
        user.email,
        verification_token,
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    limiter: RateLimiterDependency,
) -> TokenResponse:
    identifier = _rate_limit_identifier(request, "login", str(payload.email))
    await _enforce_rate_limit(limiter, identifier)
    user = await _authenticate_user(
        session,
        str(payload.email),
        payload.password,
        settings,
    )
    await limiter.reset(identifier)
    refresh_token = await create_refresh_session(session, user.id, settings)
    set_refresh_cookie(response, refresh_token, settings)
    return _token_response(user, settings)


@router.post("/token", response_model=TokenResponse)
async def oauth2_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    limiter: RateLimiterDependency,
) -> TokenResponse:
    identifier = _rate_limit_identifier(request, "token", form.username)
    await _enforce_rate_limit(limiter, identifier)
    user = await _authenticate_user(
        session,
        form.username,
        form.password,
        settings,
    )
    await limiter.reset(identifier)
    refresh_token = await create_refresh_session(session, user.id, settings)
    set_refresh_cookie(response, refresh_token, settings)
    return _token_response(user, settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    limiter: RateLimiterDependency,
) -> TokenResponse | JSONResponse:
    identifier = _rate_limit_identifier(request, "refresh")
    await _enforce_rate_limit(limiter, identifier)
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        return _refresh_credentials_error(settings)
    try:
        replacement, user = await rotate_refresh_session(
            session,
            token,
            settings,
        )
    except RefreshSessionError:
        return _refresh_credentials_error(settings)
    await limiter.reset(identifier)
    set_refresh_cookie(response, replacement, settings)
    return _token_response(user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> None:
    await revoke_refresh_session(
        session,
        request.cookies.get(settings.refresh_cookie_name),
    )
    clear_refresh_cookie(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    current_user: CurrentUserDependency,
) -> None:
    await revoke_all_user_sessions(session, current_user.id)
    clear_refresh_cookie(response, settings)


@router.post(
    "/email-verification/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_email_verification(
    payload: AccountEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    settings: SettingsDependency,
    limiter: RateLimiterDependency,
    email_sender: EmailSenderDependency,
) -> MessageResponse:
    await _enforce_rate_limit(
        limiter,
        _rate_limit_identifier(
            request,
            "email-verification-request",
            str(payload.email),
        ),
    )
    user = (
        await session.scalars(
            select(User).where(User.email == str(payload.email))
        )
    ).one_or_none()
    if user is not None and user.is_active and user.email_verified_at is None:
        token = await issue_account_token(
            session,
            user.id,
            VERIFY_EMAIL,
            timedelta(hours=settings.email_verification_expire_hours),
        )
        background_tasks.add_task(
            _deliver_account_email,
            email_sender,
            VERIFY_EMAIL,
            user.email,
            token,
        )
    return MessageResponse(message=EMAIL_VERIFICATION_REQUESTED)


@router.post(
    "/email-verification/confirm",
    response_model=MessageResponse,
)
async def confirm_email_verification(
    payload: AccountTokenRequest,
    request: Request,
    session: SessionDependency,
    limiter: RateLimiterDependency,
) -> MessageResponse:
    await _enforce_rate_limit(
        limiter,
        _rate_limit_identifier(request, "email-verification-confirm"),
    )
    try:
        stored, user = await get_valid_account_token(
            session,
            payload.token.get_secret_value(),
            VERIFY_EMAIL,
        )
    except AccountTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        ) from exc
    now = datetime.now(UTC)
    stored.consumed_at = now
    user.email_verified_at = now
    await consume_user_tokens(session, user.id, VERIFY_EMAIL, now)
    await session.commit()
    return MessageResponse(message="Email verified. You can now sign in.")


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    payload: AccountEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
    settings: SettingsDependency,
    limiter: RateLimiterDependency,
    email_sender: EmailSenderDependency,
) -> MessageResponse:
    await _enforce_rate_limit(
        limiter,
        _rate_limit_identifier(
            request,
            "password-reset-request",
            str(payload.email),
        ),
    )
    user = (
        await session.scalars(
            select(User).where(User.email == str(payload.email))
        )
    ).one_or_none()
    if user is not None and user.is_active:
        token = await issue_account_token(
            session,
            user.id,
            RESET_PASSWORD,
            timedelta(minutes=settings.password_reset_expire_minutes),
        )
        background_tasks.add_task(
            _deliver_account_email,
            email_sender,
            RESET_PASSWORD,
            user.email,
            token,
        )
    return MessageResponse(message=PASSWORD_RESET_REQUESTED)


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    session: SessionDependency,
    limiter: RateLimiterDependency,
) -> MessageResponse:
    await _enforce_rate_limit(
        limiter,
        _rate_limit_identifier(request, "password-reset-confirm"),
    )
    try:
        stored, user = await get_valid_account_token(
            session,
            payload.token.get_secret_value(),
            RESET_PASSWORD,
        )
    except AccountTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        ) from exc
    now = datetime.now(UTC)
    stored.consumed_at = now
    user.password_hash = await asyncio.to_thread(
        hash_password,
        payload.new_password,
    )
    user.email_verified_at = user.email_verified_at or now
    await consume_user_tokens(session, user.id, RESET_PASSWORD, now)
    await revoke_all_user_sessions(session, user.id)
    return MessageResponse(
        message="Password updated. Sign in with your new password."
    )


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: CurrentUserDependency) -> User:
    return current_user
