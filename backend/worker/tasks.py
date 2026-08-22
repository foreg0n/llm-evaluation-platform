from __future__ import annotations

import asyncio
import logging
import time
import uuid

from celery import current_task

from backend.db.session import SessionFactory, dispose_engine
from backend.error_monitoring import set_error_context
from backend.metrics import (
    CELERY_TASKS_IN_PROGRESS,
    observe_celery_task,
)
from backend.observability import reset_request_id, set_request_id
from backend.services.run_execution import execute_evaluation_run
from backend.worker.celery_app import celery_app
from evals.providers import generate


logger = logging.getLogger(__name__)


@celery_app.task(
    name="evals.execute_run",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)
def execute_run_task(run_id: str) -> None:
    headers = getattr(current_task.request, "headers", None) or {}
    request_id = headers.get("request_id") or run_id
    task_id = current_task.request.id or run_id
    token = set_request_id(request_id)
    set_error_context(request_id=request_id, run_id=run_id, task_id=task_id)
    task_started_at = time.perf_counter()
    CELERY_TASKS_IN_PROGRESS.inc()
    logger.info(
        "celery_run_task_started",
        extra={
            "event": "celery_run_task_started",
            "request_id": request_id,
            "run_id": run_id,
            "task_id": task_id,
        },
    )

    async def execute_and_close_pool() -> None:
        try:
            await execute_evaluation_run(
                run_id=uuid.UUID(run_id),
                session_factory=SessionFactory,
                generate_function=generate,
            )
        finally:
            # Each synchronous Celery task owns one asyncio.run() event loop.
            # Close pooled asyncpg connections before that loop disappears.
            await dispose_engine()

    try:
        asyncio.run(execute_and_close_pool())
    except Exception:
        observe_celery_task(
            outcome="failed",
            duration_seconds=time.perf_counter() - task_started_at,
        )
        logger.exception(
            "celery_run_task_failed",
            extra={
                "event": "celery_run_task_failed",
                "request_id": request_id,
                "run_id": run_id,
                "task_id": task_id,
            },
        )
        raise
    else:
        observe_celery_task(
            outcome="completed",
            duration_seconds=time.perf_counter() - task_started_at,
        )
        logger.info(
            "celery_run_task_completed",
            extra={
                "event": "celery_run_task_completed",
                "request_id": request_id,
                "run_id": run_id,
                "task_id": task_id,
            },
        )
    finally:
        CELERY_TASKS_IN_PROGRESS.dec()
        reset_request_id(token)
