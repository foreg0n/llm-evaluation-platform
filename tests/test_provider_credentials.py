from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
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
from backend.services.model_catalog import (
    ModelCatalogResult,
    ProviderModelCatalog,
    _model_ids,
    _model_request,
    get_provider_model_catalog,
)
from backend.services.provider_credentials import get_provider_credential_tester


class FakeCredentialTester:
    def __init__(self) -> None:
        self.calls: list[tuple[str, CredentialPayload]] = []

    async def test(self, model: str, payload: CredentialPayload) -> None:
        self.calls.append((model, payload))


class FakeModelCatalog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, CredentialPayload, str, bool]] = []

    async def discover(
        self,
        provider: str,
        payload: CredentialPayload,
        *,
        cache_key: str,
        force_refresh: bool = False,
    ) -> ModelCatalogResult:
        self.calls.append((provider, payload, cache_key, force_refresh))
        return ModelCatalogResult(
            models=("groq/openai/gpt-oss-20b", "groq/qwen/qwen3.6-27b"),
            source="provider",
            cached=False,
            refreshed_at=datetime(2026, 8, 27, tzinfo=UTC),
        )


@pytest.fixture
def credential_client(
    tmp_path: Path,
) -> Iterator[
    tuple[
        TestClient,
        async_sessionmaker,
        FakeCredentialTester,
        FakeModelCatalog,
    ]
]:
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
    model_catalog = FakeModelCatalog()
    asyncio.run(create_schema())
    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_provider_credential_tester] = lambda: tester
    app.dependency_overrides[get_provider_model_catalog] = lambda: model_catalog

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
        yield client, session_factory, tester, model_catalog

    asyncio.run(engine.dispose())


def test_catalog_and_encrypted_credential_crud(
    credential_client: tuple[
        TestClient, async_sessionmaker, FakeCredentialTester, FakeModelCatalog
    ],
) -> None:
    client, session_factory, _tester, _model_catalog = credential_client
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
    credential_client: tuple[
        TestClient, async_sessionmaker, FakeCredentialTester, FakeModelCatalog
    ],
) -> None:
    client, _session_factory, tester, _model_catalog = credential_client
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
    credential_client: tuple[
        TestClient, async_sessionmaker, FakeCredentialTester, FakeModelCatalog
    ],
    api_base: str,
) -> None:
    client, _session_factory, _tester, _model_catalog = credential_client
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
    credential_client: tuple[
        TestClient, async_sessionmaker, FakeCredentialTester, FakeModelCatalog
    ],
) -> None:
    client, _session_factory, _tester, model_catalog = credential_client
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
    assert (
        client.get(f"/api/v1/provider-credentials/{credential['id']}/models").status_code
        == 404
    )
    assert model_catalog.calls == []


def test_model_catalog_endpoint_discovers_without_exposing_secret(
    credential_client: tuple[
        TestClient, async_sessionmaker, FakeCredentialTester, FakeModelCatalog
    ],
) -> None:
    client, _session_factory, _tester, model_catalog = credential_client
    credential = client.post(
        "/api/v1/provider-credentials",
        json={"provider": "groq", "name": "Discovery", "api_key": "gsk_private"},
    ).json()

    response = client.get(
        f"/api/v1/provider-credentials/{credential['id']}/models?refresh=true"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["credential_id"] == credential["id"]
    assert body["provider"] == "groq"
    assert body["source"] == "provider"
    assert body["cached"] is False
    assert [entry["id"] for entry in body["models"]] == [
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.6-27b",
    ]
    assert "gsk_private" not in str(body)
    assert model_catalog.calls[0][0] == "groq"
    assert model_catalog.calls[0][1] == {
        "api_key": "gsk_private",
        "api_base": None,
    }
    assert model_catalog.calls[0][3] is True


def test_model_catalog_normalizes_caches_and_forces_refresh() -> None:
    calls: list[str] = []

    def live_loader(
        provider: str,
        _api_key: str | None,
        _api_base: str | None,
    ) -> list[str]:
        calls.append(provider)
        return [
            "qwen/qwen3.6-27b",
            "groq/openai/gpt-oss-20b",
            "qwen/qwen3.6-27b",
            "bad\nmodel",
        ]

    catalog = ProviderModelCatalog(
        live_loader=live_loader,
        fallback_loader=lambda *_args: [],
        cache_ttl_seconds=300,
    )
    payload: CredentialPayload = {"api_key": "private", "api_base": None}

    first = asyncio.run(
        catalog.discover("groq", payload, cache_key="credential:1")
    )
    cached = asyncio.run(
        catalog.discover("groq", payload, cache_key="credential:1")
    )
    refreshed = asyncio.run(
        catalog.discover(
            "groq", payload, cache_key="credential:1", force_refresh=True
        )
    )

    assert first.models == (
        "groq/openai/gpt-oss-20b",
        "groq/qwen/qwen3.6-27b",
    )
    assert first.cached is False
    assert cached.cached is True
    assert refreshed.cached is False
    assert calls == ["groq", "groq"]


def test_model_catalog_falls_back_without_leaking_loader_error() -> None:
    def failed_live_loader(*_args: object) -> list[str]:
        raise RuntimeError("provider rejected private-key")

    catalog = ProviderModelCatalog(
        live_loader=failed_live_loader,
        fallback_loader=lambda *_args: ["claude-fallback"],
        cache_ttl_seconds=0,
    )
    result = asyncio.run(
        catalog.discover(
            "anthropic",
            {"api_key": "private-key", "api_base": None},
            cache_key="credential:2",
        )
    )

    assert result.models == ("anthropic/claude-fallback",)
    assert result.source == "litellm"
    assert result.warning is not None
    assert "private-key" not in result.warning


def test_model_catalog_builds_provider_specific_requests() -> None:
    groq_url, groq_headers = _model_request("groq", "gsk_private", None)
    gemini_url, gemini_headers = _model_request("gemini", "key+/=", None)
    custom_url, custom_headers = _model_request(
        "custom", "local-key", "http://localhost:11434/v1/"
    )

    assert groq_url == "https://api.groq.com/openai/v1/models"
    assert groq_headers == {"Authorization": "Bearer gsk_private"}
    assert gemini_url == "https://generativelanguage.googleapis.com/v1beta/models"
    assert gemini_headers == {"x-goog-api-key": "key+/="}
    assert custom_url == "http://localhost:11434/v1/models"
    assert custom_headers == {"Authorization": "Bearer local-key"}


def test_model_catalog_parses_openai_and_gemini_responses() -> None:
    assert _model_ids({"data": [{"id": "alpha"}, {"id": "beta"}]}) == [
        "alpha",
        "beta",
    ]
    assert _model_ids(
        {
            "models": [
                {
                    "name": "models/gemini-pro",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/text-embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
                {"unexpected": True},
            ]
        }
    ) == ["models/gemini-pro"]
    assert _model_ids({"data": "invalid"}) == []
