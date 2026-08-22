import logging
import os

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown, worker_ready
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import CollectorRegistry, multiprocess, start_http_server

from backend.config import get_settings
from backend.error_monitoring import configure_error_monitoring
from backend.metrics import METRICS_REGISTRY
from backend.observability import configure_logging
from backend.tracing import configure_tracing, shutdown_tracing

settings = get_settings()
configure_logging(settings)
configure_error_monitoring(settings, service_name="llm-evaluation-worker")
logger = logging.getLogger(__name__)
_metrics_server: tuple[object, object] | None = None
_tracer_provider: TracerProvider | None = None
celery_app = Celery(
    "llm_evaluation_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.worker.tasks"],
)


@worker_process_init.connect(weak=False)
def initialize_worker_tracing(**_kwargs: object) -> None:
    """Initialize threaded exporters after Celery creates the worker process."""

    global _tracer_provider
    _tracer_provider = configure_tracing(
        settings,
        service_name="llm-evaluation-worker",
    )
    if _tracer_provider is not None:
        CeleryInstrumentor().instrument(tracer_provider=_tracer_provider)


celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_default_queue="evaluation_runs",
    worker_hijack_root_logger=False,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 21_600},
    result_backend_transport_options={"visibility_timeout": 21_600},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@worker_ready.connect(weak=False)
def start_worker_metrics_server(**_kwargs: object) -> None:
    """Expose process-local Celery metrics when the worker is ready."""

    global _metrics_server
    if not settings.celery_metrics_enabled or _metrics_server is not None:
        return
    registry = METRICS_REGISTRY
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    try:
        _metrics_server = start_http_server(
            settings.celery_metrics_port,
            addr=settings.celery_metrics_host,
            registry=registry,
        )
    except OSError:
        logger.exception(
            "celery_metrics_server_failed",
            extra={
                "event": "celery_metrics_server_failed",
                "metrics_host": settings.celery_metrics_host,
                "metrics_port": settings.celery_metrics_port,
            },
        )
        return
    logger.info(
        "celery_metrics_server_started",
        extra={
            "event": "celery_metrics_server_started",
            "metrics_host": settings.celery_metrics_host,
            "metrics_port": settings.celery_metrics_port,
        },
    )


@worker_process_shutdown.connect(weak=False)
def cleanup_worker_metrics_process(pid: int | None = None, **_kwargs: object) -> None:
    if pid is not None and os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(pid)
    shutdown_tracing(_tracer_provider)
