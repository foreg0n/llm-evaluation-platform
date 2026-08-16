import asyncio
import uuid

from backend.services.task_manager import RunTaskManager


def test_task_manager_cancels_active_work() -> None:
    async def scenario() -> None:
        manager = RunTaskManager()
        started = asyncio.Event()
        cleaned_up = asyncio.Event()
        run_id = uuid.uuid4()

        async def work() -> None:
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                cleaned_up.set()

        manager.start(run_id, work())
        await started.wait()

        assert await manager.cancel(run_id) is True
        assert cleaned_up.is_set()
        assert await manager.cancel(run_id) is False

    asyncio.run(scenario())


def test_task_manager_shutdown_cancels_every_task() -> None:
    async def scenario() -> None:
        manager = RunTaskManager()
        cleaned_up = 0

        async def work() -> None:
            nonlocal cleaned_up
            try:
                await asyncio.sleep(30)
            finally:
                cleaned_up += 1

        manager.start(uuid.uuid4(), work())
        manager.start(uuid.uuid4(), work())
        await asyncio.sleep(0)
        await manager.shutdown()

        assert cleaned_up == 2

    asyncio.run(scenario())
