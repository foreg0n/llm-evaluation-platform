from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

from redis.asyncio import Redis

from backend.config import Settings, get_settings


class AuthRateLimiterProtocol(Protocol):
    async def hit(self, identifier: str) -> int | None:
        """Record one attempt and return retry-after seconds when blocked."""
        ...

    async def reset(self, identifier: str) -> None:
        """Clear attempts after successful authentication."""
        ...


def _safe_key(identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"evalflow:auth-rate:{digest}"


class MemoryAuthRateLimiter:
    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, identifier: str) -> int | None:
        now = self._clock()
        cutoff = now - self._window_seconds
        async with self._lock:
            active = [
                attempted_at
                for attempted_at in self._attempts.get(identifier, [])
                if attempted_at > cutoff
            ]
            if len(active) >= self._max_attempts:
                self._attempts[identifier] = active
                return max(1, int(self._window_seconds - (now - active[0])))
            active.append(now)
            self._attempts[identifier] = active
        return None

    async def reset(self, identifier: str) -> None:
        async with self._lock:
            self._attempts.pop(identifier, None)


class RedisAuthRateLimiter:
    def __init__(
        self,
        redis_url: str,
        max_attempts: int,
        window_seconds: int,
    ) -> None:
        self._redis_url = redis_url
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds

    async def hit(self, identifier: str) -> int | None:
        client = Redis.from_url(
            self._redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        key = _safe_key(identifier)
        try:
            async with client.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.ttl(key)
                count, ttl = await pipeline.execute()
            if int(count) == 1 or int(ttl) < 0:
                await client.expire(key, self._window_seconds)
                ttl = self._window_seconds
            if int(count) > self._max_attempts:
                return max(1, int(ttl))
            return None
        finally:
            await client.aclose()

    async def reset(self, identifier: str) -> None:
        client = Redis.from_url(
            self._redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            await client.delete(_safe_key(identifier))
        finally:
            await client.aclose()


@lru_cache
def get_auth_rate_limiter() -> AuthRateLimiterProtocol:
    settings: Settings = get_settings()
    if settings.auth_rate_limit_backend == "redis":
        return RedisAuthRateLimiter(
            settings.celery_broker_url,
            settings.auth_rate_limit_attempts,
            settings.auth_rate_limit_window_seconds,
        )
    return MemoryAuthRateLimiter(
        settings.auth_rate_limit_attempts,
        settings.auth_rate_limit_window_seconds,
    )
