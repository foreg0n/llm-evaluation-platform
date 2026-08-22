from __future__ import annotations

import logging
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

from backend.config import Settings


logger = logging.getLogger(__name__)
FILTERED_VALUE = "[Filtered]"
_SENSITIVE_KEYS = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "groq_api_key",
    "password",
    "passwd",
    "proxy-authorization",
    "secret",
    "sentry_dsn",
    "set-cookie",
    "token",
    "x-api-key",
}
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}


def _normalized_key(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _scrub_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                FILTERED_VALUE
                if _normalized_key(key) in _SENSITIVE_KEYS
                else _scrub_nested(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_nested(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_nested(item) for item in value)
    return value


def scrub_sentry_event(
    event: dict[str, Any],
    _hint: dict[str, Any] | None,
) -> dict[str, Any]:
    """Remove request content and known secret fields before transport."""

    request = event.get("request")
    if isinstance(request, dict):
        for field in ("cookies", "data", "env", "query_string"):
            request.pop(field, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: (
                    FILTERED_VALUE
                    if str(key).strip().lower() in _SENSITIVE_HEADERS
                    else value
                )
                for key, value in headers.items()
            }

    for field in ("breadcrumbs", "contexts", "extra"):
        if field in event:
            event[field] = _scrub_nested(event[field])
    return event


def configure_error_monitoring(
    settings: Settings,
    *,
    service_name: str,
) -> bool:
    """Initialize privacy-safe error reporting when explicitly enabled."""

    if not settings.sentry_enabled:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"llm-evaluation-platform@{settings.app_version}",
        sample_rate=settings.sentry_error_sample_rate,
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        send_default_pii=False,
        request_bodies="never",
        include_local_variables=False,
        before_send=scrub_sentry_event,
        integrations=[
            FastApiIntegration(),
            CeleryIntegration(propagate_traces=False),
        ],
    )
    sentry_sdk.set_tag("service", service_name)
    logger.info(
        "error_monitoring_configured",
        extra={
            "event": "error_monitoring_configured",
            "error_monitoring_service": service_name,
        },
    )
    return True


def set_error_context(**values: object | None) -> None:
    """Attach non-sensitive correlation identifiers to the current event scope."""

    for key, value in values.items():
        if value is not None:
            sentry_sdk.set_tag(key, str(value))


def capture_exception(error: BaseException, **context: object | None) -> None:
    """Report a handled infrastructure failure without exposing its inputs."""

    set_error_context(**context)
    sentry_sdk.capture_exception(error)
