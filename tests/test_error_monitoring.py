from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.error_monitoring import (
    FILTERED_VALUE,
    capture_exception,
    configure_error_monitoring,
    scrub_sentry_event,
)


def test_sentry_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None, SENTRY_ENABLED=False)

    assert configure_error_monitoring(
        settings,
        service_name="test-service",
    ) is False


def test_enabled_sentry_requires_a_dsn() -> None:
    with pytest.raises(ValidationError, match="SENTRY_DSN is required"):
        Settings(_env_file=None, SENTRY_ENABLED=True, SENTRY_DSN="  ")


def test_sentry_event_scrubber_removes_request_and_nested_secrets() -> None:
    event: dict[str, Any] = {
        "request": {
            "url": "https://example.test/evaluations",
            "query_string": "token=secret",
            "data": {"prompt": "private prompt"},
            "cookies": {"session": "secret"},
            "env": {"REMOTE_ADDR": "127.0.0.1"},
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "session=secret",
                "X-API-Key": "secret",
                "User-Agent": "pytest",
            },
        },
        "extra": {
            "safe": "visible",
            "password": "secret",
            "nested": {"api_key": "secret", "count": 2},
        },
        "breadcrumbs": {
            "values": [{"data": {"token": "secret", "step": "queue"}}]
        },
    }

    scrubbed = scrub_sentry_event(event, None)

    assert scrubbed["request"]["url"] == "https://example.test/evaluations"
    assert scrubbed["request"]["headers"]["User-Agent"] == "pytest"
    assert scrubbed["request"]["headers"]["Authorization"] == FILTERED_VALUE
    assert scrubbed["request"]["headers"]["Cookie"] == FILTERED_VALUE
    assert scrubbed["request"]["headers"]["X-API-Key"] == FILTERED_VALUE
    assert "query_string" not in scrubbed["request"]
    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert "env" not in scrubbed["request"]
    assert scrubbed["extra"] == {
        "safe": "visible",
        "password": FILTERED_VALUE,
        "nested": {"api_key": FILTERED_VALUE, "count": 2},
    }
    assert scrubbed["breadcrumbs"]["values"][0]["data"] == {
        "token": FILTERED_VALUE,
        "step": "queue",
    }


def test_sentry_configuration_disables_pii_bodies_and_tracing(monkeypatch) -> None:
    from backend import error_monitoring

    init_options: dict[str, Any] = {}
    tags: list[tuple[str, str]] = []
    monkeypatch.setattr(
        error_monitoring.sentry_sdk,
        "init",
        lambda **options: init_options.update(options),
    )
    monkeypatch.setattr(
        error_monitoring.sentry_sdk,
        "set_tag",
        lambda key, value: tags.append((key, value)),
    )
    settings = Settings(
        _env_file=None,
        SENTRY_ENABLED=True,
        SENTRY_DSN="https://public@example.invalid/1",
        SENTRY_ERROR_SAMPLE_RATE=0.25,
        environment="staging",
    )

    enabled = configure_error_monitoring(
        settings,
        service_name="llm-evaluation-api",
    )

    assert enabled is True
    assert init_options["dsn"] == "https://public@example.invalid/1"
    assert init_options["environment"] == "staging"
    assert init_options["release"] == "llm-evaluation-platform@0.26.0"
    assert init_options["sample_rate"] == 0.25
    assert init_options["traces_sample_rate"] == 0.0
    assert init_options["profiles_sample_rate"] == 0.0
    assert init_options["send_default_pii"] is False
    assert init_options["request_bodies"] == "never"
    assert init_options["include_local_variables"] is False
    assert init_options["before_send"] is scrub_sentry_event
    assert len(init_options["integrations"]) == 2
    assert tags == [("service", "llm-evaluation-api")]


def test_handled_exception_capture_adds_only_explicit_context(monkeypatch) -> None:
    from backend import error_monitoring

    tags: list[tuple[str, str]] = []
    captured: list[BaseException] = []
    monkeypatch.setattr(
        error_monitoring.sentry_sdk,
        "set_tag",
        lambda key, value: tags.append((key, value)),
    )
    monkeypatch.setattr(
        error_monitoring.sentry_sdk,
        "capture_exception",
        lambda error: captured.append(error),
    )
    error = RuntimeError("database unavailable")

    capture_exception(error, request_id="request-1", run_id="run-1")

    assert tags == [("request_id", "request-1"), ("run_id", "run-1")]
    assert captured == [error]
