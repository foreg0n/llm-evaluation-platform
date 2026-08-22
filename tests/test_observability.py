import json
import logging
from types import SimpleNamespace

from backend.observability import JsonLogFormatter


def test_json_formatter_emits_machine_readable_context() -> None:
    formatter = JsonLogFormatter(
        service="test-service",
        environment="test",
        version="1.2.3",
    )
    record = logging.LogRecord(
        name="backend.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="request completed",
        args=(),
        exc_info=None,
    )
    record.event = "http_request_completed"
    record.request_id = "request-123"
    record.status_code = 200
    record.duration_ms = 12.5

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "info"
    assert payload["logger"] == "backend.test"
    assert payload["service"] == "test-service"
    assert payload["environment"] == "test"
    assert payload["version"] == "1.2.3"
    assert payload["message"] == "request completed"
    assert payload["event"] == "http_request_completed"
    assert payload["request_id"] == "request-123"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5
    assert payload["timestamp"].endswith("+00:00")


def test_celery_worker_metrics_server_uses_dedicated_registry(monkeypatch) -> None:
    from backend.worker import celery_app as worker_module

    calls = []
    server = (object(), object())
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.setattr(
        worker_module,
        "settings",
        SimpleNamespace(
            celery_metrics_enabled=True,
            celery_metrics_host="127.0.0.1",
            celery_metrics_port=19808,
        ),
    )
    monkeypatch.setattr(worker_module, "_metrics_server", None)
    monkeypatch.setattr(
        worker_module,
        "start_http_server",
        lambda port, *, addr, registry: (
            calls.append((port, addr, registry)) or server
        ),
    )

    worker_module.start_worker_metrics_server()
    worker_module.start_worker_metrics_server()

    assert len(calls) == 1
    assert calls[0][0:2] == (19808, "127.0.0.1")
    assert worker_module._metrics_server is server
