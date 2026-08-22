from celery import Celery
from opentelemetry import trace
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter

from backend.config import Settings
from backend.tracing import build_tracer_provider


class RecordingExporter(SpanExporter):
    def __init__(self) -> None:
        self.spans = []

    def export(self, spans) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def test_tracing_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.tracing_enabled is False
    assert settings.otel_trace_sample_ratio == 1.0
    assert settings.otel_exporter_otlp_endpoint.endswith("/v1/traces")


def test_tracer_provider_exports_resource_metadata_without_network() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        OTEL_TRACE_SAMPLE_RATIO=1.0,
    )
    exporter = RecordingExporter()
    provider = build_tracer_provider(
        settings,
        service_name="test-worker",
        exporter_factory=lambda _settings: exporter,
    )

    with provider.get_tracer("tests").start_as_current_span("test span"):
        pass

    assert provider.force_flush(timeout_millis=1_000)
    assert len(exporter.spans) == 1
    resource = exporter.spans[0].resource.attributes
    assert resource["service.name"] == "test-worker"
    assert resource["service.version"] == "0.25.0"
    assert resource["deployment.environment.name"] == "test"
    provider.shutdown()


def test_celery_instrumentation_propagates_parent_trace_without_network() -> None:
    settings = Settings(_env_file=None, ENVIRONMENT="test")
    exporter = RecordingExporter()
    provider = build_tracer_provider(
        settings,
        service_name="test-celery",
        exporter_factory=lambda _settings: exporter,
    )
    instrumentor = CeleryInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    app = Celery(
        "trace-test",
        broker="memory://",
        backend="cache+memory://",
    )
    app.conf.task_always_eager = True
    app.conf.task_store_eager_result = True

    @app.task(name="tests.trace_context")
    def traced_task() -> int:
        return trace.get_current_span().get_span_context().trace_id

    tracer = provider.get_tracer("tests")
    try:
        with tracer.start_as_current_span("http parent") as parent:
            parent_trace_id = parent.get_span_context().trace_id
            child_trace_id = traced_task.apply_async().get(timeout=1)

        assert child_trace_id == parent_trace_id
        assert provider.force_flush(timeout_millis=1_000)
        assert {span.context.trace_id for span in exporter.spans} == {
            parent_trace_id
        }
    finally:
        instrumentor.uninstrument()
        provider.shutdown()
