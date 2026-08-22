import asyncio
import sys
import types
import uuid

from backend.services.schedulers import CeleryRunScheduler
from backend.observability import reset_request_id, set_request_id


def test_celery_scheduler_publishes_and_revokes_without_network(
    monkeypatch,
) -> None:
    run_id = uuid.uuid4()
    published = []
    revoked = []

    class FakeTask:
        @staticmethod
        def apply_async(*, args, task_id, headers) -> None:
            published.append((args, task_id, headers))

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
        token = set_request_id("request-123")
        try:
            scheduler = CeleryRunScheduler()
            await scheduler.schedule(run_id)
            assert await scheduler.cancel(run_id) is True
        finally:
            reset_request_id(token)

    asyncio.run(scenario())

    assert published == [
        ([str(run_id)], str(run_id), {"request_id": "request-123"})
    ]
    assert revoked == [(str(run_id), False)]
