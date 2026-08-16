from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.db.base import Base
from backend.db.session import get_db_session
from backend.main import create_app
from backend.security import create_access_token


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

    with TestClient(app) as test_client:
        yield test_client

    asyncio.run(engine.dispose())


def register(
    client: TestClient,
    email: str = "user@example.com",
    password: str = "test-password",
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
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
