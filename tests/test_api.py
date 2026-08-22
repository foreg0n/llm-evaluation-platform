import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from backend.api.health import check_task_broker
from backend.config import Settings, get_settings
from backend.db.session import get_db_session
from backend.main import create_app


class StubSession:
    def __init__(self) -> None:
        self.executed_statement = ""

    async def execute(self, statement: object) -> None:
        self.executed_statement = str(statement)


def test_health_checks_database_without_real_postgres() -> None:
    app = create_app()
    session = StubSession()

    async def override_session() -> AsyncIterator[StubSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
    assert session.executed_statement == "SELECT 1"


def test_local_frontend_origin_is_allowed_by_cors() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )


def test_request_id_is_echoed_and_attached_to_completion_log(caplog) -> None:
    app = create_app()
    request_id = "frontend-run-list-123"

    with caplog.at_level(logging.INFO, logger="backend.http"):
        with TestClient(app) as client:
            response = client.get(
                "/missing-route",
                headers={
                    "Origin": "http://localhost:3000",
                    "X-Request-ID": request_id,
                },
            )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == request_id
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
    completion = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "http_request_completed"
    )
    assert completion.request_id == request_id
    assert completion.method == "GET"
    assert completion.path == "/missing-route"
    assert completion.status_code == 404
    assert completion.duration_ms >= 0


def test_invalid_request_id_is_replaced_with_uuid() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/missing-route",
            headers={"X-Request-ID": "=unsafe request id"},
        )

    assert response.status_code == 404
    generated = response.headers["X-Request-ID"]
    assert str(uuid.UUID(generated)) == generated


def test_unhandled_error_returns_generic_body_and_request_id() -> None:
    app = create_app()

    @app.get("/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/unexpected-error",
            headers={"X-Request-ID": "error-request-123"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["X-Request-ID"] == "error-request-123"
    assert "secret internal detail" not in response.text


def test_readiness_reports_local_queue_without_network() -> None:
    app = create_app()
    session = StubSession()

    async def override_session() -> AsyncIterator[StubSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        TASK_BACKEND="inprocess",
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "reachable",
        "task_backend": "inprocess",
        "broker": "not_required",
        "task_queue": "local",
    }


def test_readiness_returns_503_when_celery_broker_is_unavailable() -> None:
    app = create_app()
    session = StubSession()

    async def override_session() -> AsyncIterator[StubSession]:
        yield session

    async def unavailable_broker() -> str:
        return "unreachable"

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        TASK_BACKEND="celery",
    )
    app.dependency_overrides[check_task_broker] = unavailable_broker

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "reachable",
        "task_backend": "celery",
        "broker": "unreachable",
        "task_queue": "unavailable",
    }


def test_metrics_endpoint_exposes_bounded_http_labels() -> None:
    app = create_app()
    session = StubSession()

    async def override_session() -> AsyncIterator[StubSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP evalflow_http_requests_total" in response.text
    assert (
        'evalflow_http_requests_total{method="GET",route="/health",status_code="200"}'
        in response.text
    )


def test_celery_broker_check_uses_short_async_ping(monkeypatch) -> None:
    calls = []

    class FakeRedis:
        async def ping(self) -> bool:
            calls.append("ping")
            return True

        async def aclose(self) -> None:
            calls.append("close")

    def fake_from_url(url: str, **options):
        calls.append((url, options))
        return FakeRedis()

    monkeypatch.setattr("backend.api.health.Redis.from_url", fake_from_url)
    settings = Settings(
        _env_file=None,
        TASK_BACKEND="celery",
        CELERY_BROKER_URL="redis://example.invalid:6379/0",
        READINESS_TIMEOUT_SECONDS=0.25,
    )

    result = asyncio.run(check_task_broker(settings))

    assert result == "reachable"
    assert calls == [
        (
            "redis://example.invalid:6379/0",
            {"socket_connect_timeout": 0.25, "socket_timeout": 0.25},
        ),
        "ping",
        "close",
    ]
