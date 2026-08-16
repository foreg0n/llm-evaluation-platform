from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db.base import Base
from backend.db.session import get_db_session
from backend.main import create_app
from backend.services.schedulers import InProcessRunScheduler, get_run_scheduler
from backend.services.task_manager import RunTaskManager
from evals.models import GenerationResponse, Variant


@pytest.fixture
def run_client(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, object]]]:
    database_path = tmp_path / "run-tests.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    calls: list[tuple[str, str]] = []
    task_manager = RunTaskManager()

    async def fake_generate(prompt: str, variant: Variant) -> GenerationResponse:
        calls.append((prompt, variant.name))
        if variant.name == "Slow model":
            await asyncio.sleep(30)
        if variant.name == "Broken model":
            raise TimeoutError("mock timeout")
        return GenerationResponse(
            output="4",
            input_tokens=7,
            output_tokens=1,
            total_tokens=8,
            estimated_cost=0.0001,
            retry_count=1,
        )

    asyncio.run(create_schema())
    app = create_app()
    scheduler = InProcessRunScheduler(
        session_factory=session_factory,
        generate_function=fake_generate,
        manager=task_manager,
    )
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_run_scheduler] = lambda: scheduler

    with TestClient(app) as test_client:
        registered = test_client.post(
            "/api/v1/auth/register",
            json={"email": "runs@example.com", "password": "test-password"},
        )
        assert registered.status_code == 201
        logged_in = test_client.post(
            "/api/v1/auth/login",
            json={"email": "runs@example.com", "password": "test-password"},
        )
        assert logged_in.status_code == 200
        test_client.headers.update(
            {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
        )
        yield test_client, {"calls": calls}

    asyncio.run(engine.dispose())


def create_run_resources(
    client: TestClient,
    *,
    include_item: bool = True,
    include_broken: bool = False,
    include_slow: bool = False,
) -> tuple[dict, dict, list[dict]]:
    project = client.post(
        "/api/v1/projects", json={"name": "Run API project"}
    ).json()
    dataset = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        json={"name": "Arithmetic"},
    ).json()
    if include_item:
        response = client.post(
            f"/api/v1/datasets/{dataset['id']}/items",
            json={
                "external_id": "math-1",
                "input": "What is 2 + 2?",
                "expected_output": "4",
                "keywords": ["4"],
            },
        )
        assert response.status_code == 201

    variant_payloads = [
        {"name": "Working model", "model": "groq/qwen/test"}
    ]
    if include_broken:
        variant_payloads.append(
            {"name": "Broken model", "model": "groq/openai/test"}
        )
    if include_slow:
        variant_payloads.append(
            {"name": "Slow model", "model": "groq/qwen/slow-test"}
        )
    variants = [
        client.post(
            f"/api/v1/projects/{project['id']}/variants", json=payload
        ).json()
        for payload in variant_payloads
    ]
    return project, dataset, variants


def wait_for_terminal_run(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.01)
    raise AssertionError("Evaluation run did not reach a terminal state")


def wait_for_run_status(
    client: TestClient, run_id: str, expected_status: str
) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] == expected_status:
            return run
        if run["status"] in {"completed", "failed", "cancelled"}:
            raise AssertionError(
                f"Run reached '{run['status']}' before '{expected_status}'"
            )
        time.sleep(0.01)
    raise AssertionError(f"Run did not reach status '{expected_status}'")


def test_create_run_executes_core_and_persists_results(run_client) -> None:
    client, state = run_client
    project, dataset, variants = create_run_resources(client)

    response = client.post(
        "/api/v1/runs",
        json={
            "project_id": project["id"],
            "dataset_id": dataset["id"],
            "variant_ids": [variants[0]["id"]],
            "concurrency": 2,
        },
    )

    assert response.status_code == 202
    accepted_run = response.json()
    assert accepted_run["status"] == "pending"
    assert accepted_run["total_tasks"] == 1
    run = wait_for_terminal_run(client, accepted_run["id"])
    assert run["status"] == "completed"
    assert run["started_at"] is not None
    assert run["finished_at"] is not None
    assert len(run["results"]) == 1
    assert run["results"][0]["output"] == "4"
    assert run["results"][0]["total_tokens"] == 8
    assert run["results"][0]["metrics"]["exact_match"] == 1.0
    assert run["summary"][0]["average_quality"] == 1.0
    assert state["calls"] == [("What is 2 + 2?", "Working model")]

    detail = client.get(f"/api/v1/runs/{run['id']}")
    results = client.get(f"/api/v1/runs/{run['id']}/results")
    listed = client.get("/api/v1/runs", params={"project_id": project["id"]})
    assert detail.status_code == 200
    assert results.status_code == 200
    assert len(results.json()) == 1
    assert [entry["id"] for entry in listed.json()] == [run["id"]]


def test_provider_error_is_saved_without_failing_run(run_client) -> None:
    client, _ = run_client
    project, dataset, variants = create_run_resources(
        client, include_broken=True
    )

    response = client.post(
        "/api/v1/runs",
        json={
            "project_id": project["id"],
            "dataset_id": dataset["id"],
            "variant_ids": [variant["id"] for variant in variants],
        },
    )

    assert response.status_code == 202
    run = wait_for_terminal_run(client, response.json()["id"])
    assert run["status"] == "completed"
    assert len(run["results"]) == 2
    assert sum(result["error"] is not None for result in run["results"]) == 1
    assert sum(summary["error_count"] for summary in run["summary"]) == 1


def test_run_rejects_empty_dataset(run_client) -> None:
    client, state = run_client
    project, dataset, variants = create_run_resources(client, include_item=False)

    response = client.post(
        "/api/v1/runs",
        json={
            "project_id": project["id"],
            "dataset_id": dataset["id"],
            "variant_ids": [variants[0]["id"]],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Dataset contains no items"}
    assert state["calls"] == []


def test_run_rejects_duplicate_variant_ids(run_client) -> None:
    client, _ = run_client
    project, dataset, variants = create_run_resources(client)

    response = client.post(
        "/api/v1/runs",
        json={
            "project_id": project["id"],
            "dataset_id": dataset["id"],
            "variant_ids": [variants[0]["id"], variants[0]["id"]],
        },
    )

    assert response.status_code == 422


def test_running_evaluation_can_be_cancelled(run_client) -> None:
    client, _ = run_client
    project, dataset, variants = create_run_resources(
        client, include_slow=True
    )
    slow_variant = next(
        variant for variant in variants if variant["name"] == "Slow model"
    )
    accepted = client.post(
        "/api/v1/runs",
        json={
            "project_id": project["id"],
            "dataset_id": dataset["id"],
            "variant_ids": [slow_variant["id"]],
        },
    )
    assert accepted.status_code == 202
    wait_for_run_status(client, accepted.json()["id"], "running")

    cancelled = client.post(
        f"/api/v1/runs/{accepted.json()['id']}/cancel"
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
