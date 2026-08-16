from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db.base import Base
from backend.db.session import get_db_session
from backend.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    database_path = tmp_path / "crud-tests.db"
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
        registered = test_client.post(
            "/api/v1/auth/register",
            json={"email": "crud@example.com", "password": "test-password"},
        )
        assert registered.status_code == 201
        logged_in = test_client.post(
            "/api/v1/auth/login",
            json={"email": "crud@example.com", "password": "test-password"},
        )
        assert logged_in.status_code == 200
        test_client.headers.update(
            {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
        )
        yield test_client

    asyncio.run(engine.dispose())


def create_project(client: TestClient, name: str = "Model comparison") -> dict:
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "description": "Groq experiments"},
    )
    assert response.status_code == 201
    return response.json()


def test_project_crud_and_conflicts(client: TestClient) -> None:
    project = create_project(client)

    duplicate = client.post("/api/v1/projects", json={"name": project["name"]})
    assert duplicate.status_code == 409

    listed = client.get("/api/v1/projects", params={"limit": 1})
    assert listed.status_code == 200
    assert [entry["id"] for entry in listed.json()] == [project["id"]]

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"description": "Updated description"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated description"

    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404


def test_dataset_and_item_crud(client: TestClient) -> None:
    project = create_project(client)
    dataset_response = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        json={"name": "Reasoning set"},
    )
    assert dataset_response.status_code == 201
    dataset = dataset_response.json()

    item_response = client.post(
        f"/api/v1/datasets/{dataset['id']}/items",
        json={
            "external_id": "question-1",
            "input": "What is 2 + 2?",
            "expected_output": "4",
            "keywords": ["4"],
        },
    )
    assert item_response.status_code == 201
    item = item_response.json()

    duplicate = client.post(
        f"/api/v1/datasets/{dataset['id']}/items",
        json={
            "external_id": "question-1",
            "input": "Duplicate",
            "expected_output": "Duplicate",
        },
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/v1/dataset-items/{item['id']}", json={"keywords": ["four"]}
    )
    assert updated.status_code == 200
    assert updated.json()["keywords"] == ["four"]

    listed = client.get(f"/api/v1/datasets/{dataset['id']}/items")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    assert client.delete(f"/api/v1/dataset-items/{item['id']}").status_code == 204
    assert client.delete(f"/api/v1/datasets/{dataset['id']}").status_code == 204


def test_import_jsonl_dataset_and_items_atomically(client: TestClient) -> None:
    project = create_project(client)
    content = "\n".join(
        json.dumps(item)
        for item in [
            {
                "id": "capital-france",
                "input": "What is the capital of France?",
                "expected_output": "Paris",
                "keywords": ["Paris"],
            },
            {
                "external_id": "addition",
                "input": "What is 5 + 7?",
                "expected_output": "12",
                "keywords": ["12"],
            },
        ]
    )

    response = client.post(
        f"/api/v1/projects/{project['id']}/datasets/import",
        data={"name": "Uploaded benchmark", "description": "Imported JSONL"},
        files={"file": ("questions.jsonl", content, "application/x-ndjson")},
    )

    assert response.status_code == 201
    assert response.json()["item_count"] == 2
    dataset = response.json()["dataset"]
    assert dataset["name"] == "Uploaded benchmark"
    items = client.get(f"/api/v1/datasets/{dataset['id']}/items")
    assert items.status_code == 200
    assert {item["external_id"] for item in items.json()} == {
        "capital-france",
        "addition",
    }


def test_import_json_document_metadata_and_reject_invalid_file(
    client: TestClient,
) -> None:
    project = create_project(client)
    document = {
        "name": "JSON benchmark",
        "description": "Metadata comes from the file",
        "items": [
            {
                "id": "valid-item",
                "input": "Return ok",
                "expected_output": "ok",
            }
        ],
    }
    imported = client.post(
        f"/api/v1/projects/{project['id']}/datasets/import",
        files={
            "file": (
                "benchmark.json",
                json.dumps(document),
                "application/json",
            )
        },
    )
    assert imported.status_code == 201
    assert imported.json()["dataset"]["name"] == "JSON benchmark"

    invalid = client.post(
        f"/api/v1/projects/{project['id']}/datasets/import",
        data={"name": "Broken upload"},
        files={
            "file": (
                "broken.jsonl",
                '{"id":"missing-input","expected_output":"answer"}',
                "application/x-ndjson",
            )
        },
    )
    assert invalid.status_code == 422
    assert "input" in invalid.json()["detail"]
    datasets = client.get(f"/api/v1/projects/{project['id']}/datasets")
    assert [dataset["name"] for dataset in datasets.json()] == ["JSON benchmark"]


def test_variant_crud_and_validation(client: TestClient) -> None:
    project = create_project(client)
    endpoint = f"/api/v1/projects/{project['id']}/variants"

    invalid = client.post(
        endpoint,
        json={"name": "Invalid", "model": "qwen/test", "timeout_seconds": 0},
    )
    assert invalid.status_code == 422

    created = client.post(
        endpoint,
        json={
            "name": "Qwen",
            "model": "groq/qwen/qwen3.6-27b",
            "temperature": 0,
            "max_tokens": 500,
        },
    )
    assert created.status_code == 201
    variant = created.json()
    assert variant["provider"] == "litellm"
    assert variant["max_retries"] == 2

    updated = client.patch(
        f"/api/v1/variants/{variant['id']}", json={"timeout_seconds": 60}
    )
    assert updated.status_code == 200
    assert updated.json()["timeout_seconds"] == 60

    deleted = client.delete(f"/api/v1/variants/{variant['id']}")
    assert deleted.status_code == 204


def test_nested_create_requires_existing_parent(client: TestClient) -> None:
    missing_id = "00000000-0000-0000-0000-000000000001"

    response = client.post(
        f"/api/v1/projects/{missing_id}/datasets", json={"name": "Dataset"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}
