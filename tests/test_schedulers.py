import asyncio
import sys
import types
import uuid

from backend.services.schedulers import CeleryRunScheduler


def test_celery_scheduler_publishes_and_revokes_without_network(
    monkeypatch,
) -> None:
    run_id = uuid.uuid4()
    published = []
    revoked = []

    class FakeTask:
        @staticmethod
        def apply_async(*, args, task_id) -> None:
            published.append((args, task_id))

    class FakeControl:
        @staticmethod
        def revoke(task_id, terminate) -> None:
            revoked.append((task_id, terminate))

    tasks_module = types.ModuleType("backend.worker.tasks")
    tasks_module.execute_run_task = FakeTask
    app_module = types.ModuleType("backend.worker.celery_app")
    app_module.celery_app = types.SimpleNamespace(control=FakeControl())
    monkeypatch.setitem(sys.modules, "backend.worker.tasks", tasks_module)
    monkeypatch.setitem(sys.modules, "backend.worker.celery_app", app_module)

    async def scenario() -> None:
        scheduler = CeleryRunScheduler()
        await scheduler.schedule(run_id)
        assert await scheduler.cancel(run_id) is True

    asyncio.run(scenario())

    assert published == [([str(run_id)], str(run_id))]
    assert revoked == [(str(run_id), False)]
