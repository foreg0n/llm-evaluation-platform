from celery import Celery

from backend.config import get_settings

settings = get_settings()
celery_app = Celery(
    "llm_evaluation_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.worker.tasks"],
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_default_queue="evaluation_runs",
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 21_600},
    result_backend_transport_options={"visibility_timeout": 21_600},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
