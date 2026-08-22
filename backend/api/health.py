from contextlib import suppress
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.db.session import get_db_session
from backend.metrics import READINESS_CHECKS

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str


BrokerStatus = Literal["reachable", "unreachable", "not_required"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["reachable", "unreachable"]
    task_backend: Literal["inprocess", "celery"]
    broker: BrokerStatus
    task_queue: Literal["ready", "unavailable", "local"]


SettingsDependency = Annotated[Settings, Depends(get_settings)]


async def check_task_broker(settings: SettingsDependency) -> BrokerStatus:
    if settings.task_backend == "inprocess":
        return "not_required"

    client = Redis.from_url(
        settings.celery_broker_url,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        return "reachable" if await client.ping() else "unreachable"
    except (RedisError, TimeoutError, OSError):
        return "unreachable"
    finally:
        with suppress(Exception):
            await client.aclose()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HealthResponse:
    """Report readiness after verifying the database connection."""

    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="reachable")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: SettingsDependency,
    broker: Annotated[BrokerStatus, Depends(check_task_broker)],
) -> ReadinessResponse:
    """Report whether database and configured task infrastructure are usable."""

    try:
        await session.execute(text("SELECT 1"))
        database: Literal["reachable", "unreachable"] = "reachable"
    except Exception:
        database = "unreachable"

    queue_ready = settings.task_backend == "inprocess" or broker == "reachable"
    is_ready = database == "reachable" and queue_ready
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    READINESS_CHECKS.labels(component="database", status=database).inc()
    READINESS_CHECKS.labels(component="broker", status=broker).inc()
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        database=database,
        task_backend=settings.task_backend,
        broker=broker,
        task_queue=(
            "local"
            if settings.task_backend == "inprocess"
            else "ready" if broker == "reachable" else "unavailable"
        ),
    )
