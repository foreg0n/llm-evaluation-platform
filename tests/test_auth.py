from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.db.base import Base
from backend.db.models import AccountActionToken, RefreshSession
from backend.db.session import get_db_session
from backend.main import create_app
from backend.security import (
    create_access_token,
    hash_account_action_token,
    hash_refresh_token,
)
from backend.services.auth_rate_limit import (
    MemoryAuthRateLimiter,
    get_auth_rate_limiter,
)
from backend.services.auth_sessions import REFRESH_COOKIE_PATH
from backend.services.email_delivery import get_email_sender


class CapturingEmailSender:
    def __init__(self) -> None:
        self.verification_tokens: dict[str, list[str]] = {}
        self.password_reset_tokens: dict[str, list[str]] = {}

    async def send_email_verification(self, recipient: str, token: str) -> None:
        self.verification_tokens.setdefault(recipient, []).append(token)

    async def send_password_reset(self, recipient: str, token: str) -> None:
        self.password_reset_tokens.setdefault(recipient, []).append(token)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database_path = tmp_path / "auth-tests.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    asyncio.run(create_schema())
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    email_sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: email_sender

    with TestClient(app) as test_client:
        test_client.app.state.auth_test_session_factory = session_factory
        test_client.app.state.auth_test_email_sender = email_sender
        yield test_client

    asyncio.run(engine.dispose())


def register(
    client: TestClient,
    email: str = "user@example.com",
    password: str = "test-password",
    *,
    verify: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    if verify:
        normalized_email = email.strip().lower()
        sender = client.app.state.auth_test_email_sender
        token = sender.verification_tokens[normalized_email][-1]
        verified = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": token},
        )
        assert verified.status_code == 200
    return response.json()


def login_headers(
    client: TestClient,
    email: str = "user@example.com",
    password: str = "test-password",
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_login_and_read_current_user(client: TestClient) -> None:
    user = register(client, "  USER@Example.com ")

    assert user["email"] == "user@example.com"
    assert "password" not in user
    assert "password_hash" not in user

    headers = login_headers(client)
    me = client.get("/api/v1/auth/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["id"] == user["id"]


def test_login_issues_http_only_refresh_cookie_and_stores_only_hash(
    client: TestClient,
) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    settings = get_settings()
    refresh_token = response.cookies.get(settings.refresh_cookie_name)

    assert response.status_code == 200
    assert refresh_token is not None
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert f"path={REFRESH_COOKIE_PATH}" in set_cookie
    assert refresh_token not in response.text

    async def read_session() -> RefreshSession:
        factory = client.app.state.auth_test_session_factory
        async with factory() as session:
            return (await session.scalars(select(RefreshSession))).one()

    stored = asyncio.run(read_session())
    assert stored.token_hash == hash_refresh_token(refresh_token)
    assert refresh_token not in stored.token_hash


def test_refresh_rotates_token_and_replay_revokes_the_family(
    client: TestClient,
) -> None:
    user = register(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    cookie_name = get_settings().refresh_cookie_name
    original_token = login_response.cookies.get(cookie_name)
    assert original_token is not None

    refreshed = client.post("/api/v1/auth/refresh")
    replacement_token = refreshed.cookies.get(cookie_name)
    assert refreshed.status_code == 200
    assert replacement_token is not None
    assert replacement_token != original_token
    assert client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {refreshed.json()['access_token']}"
        },
    ).json()["id"] == user["id"]

    replayed = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{cookie_name}={original_token}"},
    )
    assert replayed.status_code == 401
    rejected_replacement = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{cookie_name}={replacement_token}"},
    )
    assert rejected_replacement.status_code == 401

    async def read_sessions() -> list[RefreshSession]:
        factory = client.app.state.auth_test_session_factory
        async with factory() as session:
            return list((await session.scalars(select(RefreshSession))).all())

    sessions = asyncio.run(read_sessions())
    assert len(sessions) == 2
    assert all(session.revoked_at is not None for session in sessions)


def test_logout_revokes_refresh_session_and_clears_cookie(
    client: TestClient,
) -> None:
    register(client)
    client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )

    logged_out = client.post("/api/v1/auth/logout")

    assert logged_out.status_code == 204
    assert "max-age=0" in logged_out.headers["set-cookie"].lower()
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_all_revokes_every_user_session(client: TestClient) -> None:
    register(client)
    first = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    second = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    response = client.post(
        "/api/v1/auth/logout-all",
        headers={
            "Authorization": f"Bearer {second.json()['access_token']}"
        },
    )

    assert response.status_code == 204
    cookie_name = get_settings().refresh_cookie_name
    assert client.post(
        "/api/v1/auth/refresh",
        headers={
            "Cookie": f"{cookie_name}={first.cookies.get(cookie_name)}"
        },
    ).status_code == 401


def test_repeated_bad_logins_are_rate_limited(client: TestClient) -> None:
    register(client)
    limiter = MemoryAuthRateLimiter(max_attempts=2, window_seconds=60)
    client.app.dependency_overrides[get_auth_rate_limiter] = lambda: limiter
    payload = {"email": "user@example.com", "password": "wrong-password"}

    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    blocked = client.post("/api/v1/auth/login", json=payload)

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert "Too many authentication attempts" in blocked.json()["detail"]


def test_duplicate_registration_and_bad_password_are_rejected(
    client: TestClient,
) -> None:
    register(client)

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "USER@example.com", "password": "another-password"},
    )
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )

    assert duplicate.status_code == 409
    assert bad_login.status_code == 401
    assert bad_login.json() == {"detail": "Incorrect email or password"}


def test_oauth2_form_token_and_protected_endpoint(client: TestClient) -> None:
    register(client)

    token_response = client.post(
        "/api/v1/auth/token",
        data={"username": "user@example.com", "password": "test-password"},
    )

    assert token_response.status_code == 200
    assert token_response.json()["token_type"] == "bearer"
    unauthorized = client.get("/api/v1/projects")
    assert unauthorized.status_code == 401


def test_users_cannot_read_each_others_projects(client: TestClient) -> None:
    first = register(client, "first@example.com")
    first_headers = login_headers(client, "first@example.com")
    first_project = client.post(
        "/api/v1/projects",
        json={"name": "Private project"},
        headers=first_headers,
    )
    assert first_project.status_code == 201
    assert first_project.json()["owner_id"] == first["id"]

    register(client, "second@example.com")
    second_headers = login_headers(client, "second@example.com")

    hidden = client.get(
        f"/api/v1/projects/{first_project.json()['id']}",
        headers=second_headers,
    )
    listed = client.get("/api/v1/projects", headers=second_headers)
    same_name = client.post(
        "/api/v1/projects",
        json={"name": "Private project"},
        headers=second_headers,
    )

    assert hidden.status_code == 404
    assert listed.json() == []
    assert same_name.status_code == 201


def test_expired_access_token_is_rejected(client: TestClient) -> None:
    user = register(client)
    token = create_access_token(
        user_id=uuid.UUID(user["id"]),
        settings=get_settings(),
        expires_delta=timedelta(seconds=-1),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_unverified_user_must_confirm_one_time_hashed_token(
    client: TestClient,
) -> None:
    strict_settings = get_settings().model_copy(
        update={"require_email_verification": True}
    )
    client.app.dependency_overrides[get_settings] = lambda: strict_settings
    user = register(client, verify=False)
    sender = client.app.state.auth_test_email_sender
    raw_token = sender.verification_tokens["user@example.com"][-1]

    rejected = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "Email verification required"

    async def read_token() -> AccountActionToken:
        factory = client.app.state.auth_test_session_factory
        async with factory() as session:
            return (
                await session.scalars(
                    select(AccountActionToken).where(
                        AccountActionToken.purpose == "verify_email"
                    )
                )
            ).one()

    stored = asyncio.run(read_token())
    assert stored.user_id == uuid.UUID(user["id"])
    assert stored.token_hash == hash_account_action_token(raw_token)
    assert raw_token not in stored.token_hash

    confirmed = client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": raw_token},
    )
    replayed = client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": raw_token},
    )
    accepted = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )

    assert confirmed.status_code == 200
    assert replayed.status_code == 400
    assert accepted.status_code == 200


def test_verification_and_reset_requests_do_not_reveal_account_existence(
    client: TestClient,
) -> None:
    register(client)

    known_verification = client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "user@example.com"},
    )
    unknown_verification = client.post(
        "/api/v1/auth/email-verification/request",
        json={"email": "missing@example.com"},
    )
    known_reset = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "user@example.com"},
    )
    unknown_reset = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "missing@example.com"},
    )

    assert known_verification.status_code == 202
    assert unknown_verification.status_code == 202
    assert known_verification.json() == unknown_verification.json()
    assert known_reset.status_code == 202
    assert unknown_reset.status_code == 202
    assert known_reset.json() == unknown_reset.json()


def test_password_reset_is_one_time_and_revokes_existing_sessions(
    client: TestClient,
) -> None:
    register(client)
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    cookie_name = get_settings().refresh_cookie_name
    original_refresh = logged_in.cookies.get(cookie_name)
    assert original_refresh is not None

    requested = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "user@example.com"},
    )
    sender = client.app.state.auth_test_email_sender
    reset_token = sender.password_reset_tokens["user@example.com"][-1]
    assert requested.status_code == 202

    changed = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "new-test-password"},
    )
    replayed = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "other-password"},
    )
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "test-password"},
    )
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "new-test-password"},
    )
    old_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"{cookie_name}={original_refresh}"},
    )

    assert changed.status_code == 200
    assert replayed.status_code == 400
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert old_refresh.status_code == 401


def test_password_reset_commits_without_session_helper_side_effect(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(client)
    requested = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "user@example.com"},
    )
    sender = client.app.state.auth_test_email_sender
    reset_token = sender.password_reset_tokens["user@example.com"][-1]

    async def revoke_without_commit(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "backend.api.auth.revoke_all_user_sessions",
        revoke_without_commit,
    )
    changed = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "new-test-password"},
    )
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "new-test-password"},
    )

    assert requested.status_code == 202
    assert changed.status_code == 200
    assert logged_in.status_code == 200


def test_expired_password_reset_token_is_rejected(client: TestClient) -> None:
    register(client)
    client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "user@example.com"},
    )
    sender = client.app.state.auth_test_email_sender
    raw_token = sender.password_reset_tokens["user@example.com"][-1]

    async def expire_token() -> None:
        factory = client.app.state.auth_test_session_factory
        async with factory() as session:
            stored = (
                await session.scalars(
                    select(AccountActionToken).where(
                        AccountActionToken.token_hash
                        == hash_account_action_token(raw_token)
                    )
                )
            ).one()
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire_token())
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "new-test-password"},
    )

    assert response.status_code == 400
