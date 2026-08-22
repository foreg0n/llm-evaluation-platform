from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.config import Settings
from backend.metrics import observe_http_request


REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_request_id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_structured_fields = (
    "event",
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "run_id",
    "task_id",
    "total_tasks",
    "completed_tasks",
    "metrics_host",
    "metrics_port",
)


def get_request_id() -> str | None:
    """Return the correlation ID for the current async execution context."""

    return _request_id.get()


def set_request_id(value: str | None) -> Token[str | None]:
    """Set the current correlation ID and return a token for resetting it."""

    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def _resolve_request_id(candidate: str | None) -> str:
    if candidate:
        normalized = candidate.strip()
        if _request_id_pattern.fullmatch(normalized):
            return normalized
    return str(uuid.uuid4())


class JsonLogFormatter(logging.Formatter):
    """Serialize application logs as one JSON object per line."""

    def __init__(self, *, service: str, environment: str, version: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "service": self.service,
            "environment": self.environment,
            "version": self.version,
            "message": record.getMessage(),
        }
        contextual_request_id = getattr(record, "request_id", None) or get_request_id()
        if contextual_request_id:
            payload["request_id"] = contextual_request_id
        for field in _structured_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ContextTextFormatter(logging.Formatter):
    """Readable local format that still includes the current request ID."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id() or "-"
        return super().format(record)


def configure_logging(settings: Settings) -> None:
    """Install one idempotent application handler on the root logger."""

    root = logging.getLogger()
    level = getattr(logging, settings.log_level)
    handler = next(
        (
            current
            for current in root.handlers
            if getattr(current, "_evalflow_handler", False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        setattr(handler, "_evalflow_handler", True)
        root.addHandler(handler)
    handler.setLevel(level)
    if settings.log_format == "json":
        handler.setFormatter(
            JsonLogFormatter(
                service="llm-evaluation-api",
                environment=settings.environment,
                version=settings.app_version,
            )
        )
    else:
        handler.setFormatter(
            ContextTextFormatter(
                "%(asctime)s %(levelname)s %(name)s "
                "request_id=%(request_id)s %(message)s"
            )
        )
    root.setLevel(level)


class RequestContextMiddleware:
    """Attach a safe correlation ID and emit one completion log per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("backend.http")

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(
            Headers(scope=scope).get(REQUEST_ID_HEADER)
        )
        scope.setdefault("state", {})["request_id"] = request_id
        token = set_request_id(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            duration_seconds = time.perf_counter() - started_at
            route = getattr(scope.get("route"), "path", "__unmatched__")
            observe_http_request(
                method=scope["method"],
                route=route,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            self.logger.exception(
                "http_request_failed",
                extra={
                    "event": "http_request_failed",
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
            )
            raise
        else:
            duration_seconds = time.perf_counter() - started_at
            route = getattr(scope.get("route"), "path", "__unmatched__")
            observe_http_request(
                method=scope["method"],
                route=route,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            self.logger.info(
                "http_request_completed",
                extra={
                    "event": "http_request_completed",
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
            )
        finally:
            reset_request_id(token)
