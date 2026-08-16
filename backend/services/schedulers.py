from __future__ import annotations

import asyncio
import uuid
from functools import lru_cache
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.db.session import SessionFactory
from backend.services.run_execution import execute_evaluation_run
from backend.services.task_manager import RunTaskManager, task_manager
from evals.providers import generate
from evals.runner import GenerateFunction


class RunScheduler(Protocol):
    async def schedule(self, run_id: uuid.UUID) -> None: ...

    async def cancel(self, run_id: uuid.UUID) -> bool: ...


class InProcessRunScheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = SessionFactory,
        generate_function: GenerateFunction = generate,
        manager: RunTaskManager = task_manager,
    ) -> None:
        self._session_factory = session_factory
        self._generate_function = generate_function
        self._manager = manager

    async def schedule(self, run_id: uuid.UUID) -> None:
        self._manager.start(
            run_id,
            execute_evaluation_run(
                run_id=run_id,
                session_factory=self._session_factory,
                generate_function=self._generate_function,
            ),
        )

    async def cancel(self, run_id: uuid.UUID) -> bool:
        return await self._manager.cancel(run_id)


class CeleryRunScheduler:
    async def schedule(self, run_id: uuid.UUID) -> None:
        from backend.worker.tasks import execute_run_task

        await asyncio.to_thread(
            execute_run_task.apply_async,
            args=[str(run_id)],
            task_id=str(run_id),
        )

    async def cancel(self, run_id: uuid.UUID) -> bool:
        from backend.worker.celery_app import celery_app

        await asyncio.to_thread(
            celery_app.control.revoke,
            str(run_id),
            terminate=False,
        )
        return True


@lru_cache
def get_run_scheduler() -> RunScheduler:
    settings = get_settings()
    if settings.task_backend == "celery":
        return CeleryRunScheduler()
    return InProcessRunScheduler()
