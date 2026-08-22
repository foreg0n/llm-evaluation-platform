from __future__ import annotations

import logging
from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from backend.config import Settings


logger = logging.getLogger(__name__)
ExporterFactory = Callable[[Settings], SpanExporter]
_tracer_provider: TracerProvider | None = None


def current_trace_ids() -> tuple[str | None, str | None]:
    """Return lowercase hexadecimal IDs for the active sampled or unsampled span."""

    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None, None
    return f"{context.trace_id:032x}", f"{context.span_id:016x}"


def _default_exporter_factory(settings: Settings) -> SpanExporter:
    return OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        timeout=settings.otel_export_timeout_seconds,
    )


def build_tracer_provider(
    settings: Settings,
    *,
    service_name: str,
    exporter_factory: ExporterFactory = _default_exporter_factory,
) -> TracerProvider:
    """Build an SDK provider without changing OpenTelemetry global state."""

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": settings.app_version,
            "deployment.environment.name": settings.environment,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(exporter_factory(settings))
    )
    return provider


def configure_tracing(
    settings: Settings,
    *,
    service_name: str,
) -> TracerProvider | None:
    """Configure one process-global OTLP provider when tracing is enabled."""

    global _tracer_provider
    if not settings.tracing_enabled:
        return None
    if _tracer_provider is not None:
        return _tracer_provider

    provider = build_tracer_provider(settings, service_name=service_name)
    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    logger.info(
        "tracing_configured",
        extra={
            "event": "tracing_configured",
            "tracing_service": service_name,
            "tracing_endpoint": settings.otel_exporter_otlp_endpoint,
        },
    )
    return provider


def shutdown_tracing(provider: TracerProvider | None) -> None:
    """Flush queued spans without making tracing required for shutdown."""

    if provider is None:
        return
    try:
        provider.force_flush(timeout_millis=5_000)
        provider.shutdown()
    except Exception:
        logger.exception("tracing_shutdown_failed")
