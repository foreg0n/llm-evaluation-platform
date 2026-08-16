from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any


class RunTaskManager:
    """Own in-process evaluation tasks and support cooperative cancellation."""

    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    def start(self, run_id: uuid.UUID, work: Coroutine[Any, Any, None]) -> None:
        if run_id in self._tasks:
            work.close()
            raise RuntimeError(f"Run {run_id} is already scheduled")

        task = asyncio.create_task(work, name=f"evaluation-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(
            lambda completed, current_run_id=run_id: self._discard(
                current_run_id, completed
            )
        )

    async def cancel(self, run_id: uuid.UUID) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _discard(
        self, run_id: uuid.UUID, completed: asyncio.Task[None]
    ) -> None:
        if self._tasks.get(run_id) is completed:
            self._tasks.pop(run_id, None)
        if not completed.cancelled():
            completed.exception()


task_manager = RunTaskManager()


def get_task_manager() -> RunTaskManager:
    return task_manager
