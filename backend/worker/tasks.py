from __future__ import annotations

import asyncio
import uuid

from backend.db.session import SessionFactory, dispose_engine
from backend.services.run_execution import execute_evaluation_run
from backend.worker.celery_app import celery_app
from evals.providers import generate


@celery_app.task(
    name="evals.execute_run",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)
def execute_run_task(run_id: str) -> None:
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

    asyncio.run(execute_and_close_pool())
