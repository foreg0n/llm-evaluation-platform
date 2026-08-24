from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import (
    DEVELOPMENT_CREDENTIAL_ENCRYPTION_KEY,
    Settings,
)
from backend.credential_security import (
    CredentialCipher,
    CredentialDecryptionError,
    CredentialPayload,
)
from backend.db.base import Base
from backend.db.models import ProviderCredential
from backend.db.session import get_db_session
from backend.main import create_app
from backend.services.provider_credentials import get_provider_credential_tester


class FakeCredentialTester:
    def __init__(self) -> None:
        self.calls: list[tuple[str, CredentialPayload]] = []

    async def test(self, model: str, payload: CredentialPayload) -> None:
        self.calls.append((model, payload))


@pytest.fixture
def credential_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, async_sessionmaker, FakeCredentialTester]]:
    database_path = tmp_path / "provider-credentials.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    tester = FakeCredentialTester()
    asyncio.run(create_schema())
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_provider_credential_tester] = lambda: tester

    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "owner@example.com", "password": "test-password"},
        )
        assert registered.status_code == 201
        logged_in = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "test-password"},
        )
        client.headers.update(
            {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
        )
        yield client, session_factory, tester

    asyncio.run(engine.dispose())


def test_catalog_and_encrypted_credential_crud(
    credential_client: tuple[TestClient, async_sessionmaker, FakeCredentialTester],
) -> None:
    client, session_factory, _tester = credential_client
    catalog = client.get("/api/v1/providers/catalog")
    assert catalog.status_code == 200
    assert {entry["slug"] for entry in catalog.json()} >= {
        "groq",
        "openai",
        "anthropic",
        "gemini",
        "custom",
    }

    created = client.post(
        "/api/v1/provider-credentials",
        json={
            "provider": "anthropic",
            "name": "Personal Claude",
            "api_key": "sk-ant-private-value",
        },
    )
    assert created.status_code == 201
    credential = created.json()
    assert credential["key_hint"] == "••••alue"
    assert credential["status"] == "untested"
    assert "api_key" not in credential
    assert "encrypted_payload" not in credential

    async def read_stored() -> ProviderCredential:
        async with session_factory() as session:
            return (await session.scalars(select(ProviderCredential))).one()

    stored = asyncio.run(read_stored())
    assert "sk-ant-private-value" not in stored.encrypted_payload

    listed = client.get("/api/v1/provider-credentials")
    assert listed.status_code == 200
    assert [entry["id"] for entry in listed.json()] == [credential["id"]]

    updated = client.patch(
        f"/api/v1/provider-credentials/{credential['id']}",
        json={"name": "Claude work", "api_key": "replacement-key"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Claude work"
    assert updated.json()["key_hint"] == "••••-key"
    assert "replacement-key" not in str(updated.json())


def test_custom_provider_requires_base_url_and_test_is_explicit(
    credential_client: tuple[TestClient, async_sessionmaker, FakeCredentialTester],
) -> None:
    client, _session_factory, tester = credential_client
    missing_base = client.post(
        "/api/v1/provider-credentials",
        json={"provider": "custom", "name": "Local", "api_key": "local-key"},
    )
    assert missing_base.status_code == 422

    created = client.post(
        "/api/v1/provider-credentials",
        json={
            "provider": "custom",
            "name": "Internal gateway",
            "api_key": "gateway-key",
            "api_base": "http://localhost:11434/v1/",
        },
    ).json()
    assert tester.calls == []

    checked = client.post(
        f"/api/v1/provider-credentials/{created['id']}/test",
        json={"model": "openai/local-model"},
    )
    assert checked.status_code == 200
    assert checked.json()["status"] == "connected"
    assert tester.calls == [
        (
            "openai/local-model",
            {"api_key": "gateway-key", "api_base": "http://localhost:11434/v1"},
        )
    ]


@pytest.mark.parametrize(
    "api_base",
    [
        "localhost:11434/v1",
        "https://",
        "https://user:password@example.com/v1",
        "https://example.com/v1#secret",
    ],
)
def test_custom_provider_rejects_unsafe_or_incomplete_base_urls(
    credential_client: tuple[TestClient, async_sessionmaker, FakeCredentialTester],
    api_base: str,
) -> None:
    client, _session_factory, _tester = credential_client
    response = client.post(
        "/api/v1/provider-credentials",
        json={
            "provider": "custom",
            "name": "Unsafe gateway",
            "api_key": "gateway-key",
            "api_base": api_base,
        },
    )
    assert response.status_code == 422


def test_credential_cipher_rejects_another_installation_key() -> None:
    original = CredentialCipher(Fernet.generate_key().decode("ascii"))
    another = CredentialCipher(Fernet.generate_key().decode("ascii"))
    encrypted = original.encrypt({"api_key": "private-key", "api_base": None})

    with pytest.raises(CredentialDecryptionError):
        another.decrypt(encrypted)


def test_production_rejects_development_credential_encryption_key() -> None:
    with pytest.raises(ValidationError, match="CREDENTIAL_ENCRYPTION_KEY"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY="a" * 64,
            CREDENTIAL_ENCRYPTION_KEY=DEVELOPMENT_CREDENTIAL_ENCRYPTION_KEY,
        )


def test_settings_reject_invalid_credential_encryption_key() -> None:
    with pytest.raises(ValidationError, match="valid Fernet key"):
        Settings(CREDENTIAL_ENCRYPTION_KEY="not-a-fernet-key")


def test_credentials_are_isolated_and_cannot_be_deleted_while_attached(
    credential_client: tuple[TestClient, async_sessionmaker, FakeCredentialTester],
) -> None:
    client, _session_factory, _tester = credential_client
    credential = client.post(
        "/api/v1/provider-credentials",
        json={"provider": "groq", "name": "Personal", "api_key": "gsk_secret"},
    ).json()
    project = client.post("/api/v1/projects", json={"name": "Credentials"}).json()
    variant = client.post(
        f"/api/v1/projects/{project['id']}/variants",
        json={
            "name": "Qwen",
            "model": "groq/qwen/test",
            "credential_id": credential["id"],
        },
    )
    assert variant.status_code == 201
    assert variant.json()["credential_id"] == credential["id"]
    blocked = client.delete(f"/api/v1/provider-credentials/{credential['id']}")
    assert blocked.status_code == 409

    second_user = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "test-password"},
    )
    assert second_user.status_code == 201
    second_login = client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "test-password"},
    ).json()
    client.headers.update(
        {"Authorization": f"Bearer {second_login['access_token']}"}
    )
    assert client.get("/api/v1/provider-credentials").json() == []
    assert (
        client.patch(
            f"/api/v1/provider-credentials/{credential['id']}",
            json={"name": "stolen"},
        ).status_code
        == 404
    )
