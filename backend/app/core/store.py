"""Tiny KV abstraction: Redis when reachable, otherwise a process-local fallback (single worker)."""
from __future__ import annotations

import asyncio
import logging
import time

import redis.asyncio as aioredis

from app.core.config import get_settings

log = logging.getLogger("nexus.store")


class Store:
    def __init__(self, redis_url: str | None):
        self._url = redis_url
        self.redis: aioredis.Redis | None = None
        self._mem: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if not self._url:
            log.warning("REDIS_URL not set: using in-process store (single worker only)")
            return
        try:
            client = aioredis.from_url(self._url, decode_responses=True)
            await client.ping()
            self.redis = client
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis unavailable (%s): falling back to in-process store", exc)

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()

    async def incr_window(self, key: str, window: int) -> int:
        """Fixed-window counter. Returns the new count."""
        if self.redis:
            try:
                pipe = self.redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, window, nx=True)
                count, _ = await pipe.execute()
                return int(count)
            except Exception:  # noqa: BLE001
                log.warning("Redis error in incr_window; using memory fallback")
        async with self._lock:
            now = time.monotonic()
            count, reset = self._mem.get(key, (0, now + window))
            if now >= reset:
                count, reset = 0, now + window
            count += 1
            self._mem[key] = (count, reset)
            if len(self._mem) > 50_000:
                self._mem = {k: v for k, v in self._mem.items() if v[1] > now}
            return count

    async def set_once(self, key: str, ttl: int) -> bool:
        """True the first time a key is seen (used for single-use WS tickets)."""
        if self.redis:
            try:
                return bool(await self.redis.set(key, "1", nx=True, ex=ttl))
            except Exception:  # noqa: BLE001
                log.warning("Redis error in set_once; using memory fallback")
        async with self._lock:
            now = time.monotonic()
            if key in self._mem and self._mem[key][1] > now:
                return False
            self._mem[key] = (1, now + ttl)
            return True


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store(get_settings().redis_url)
    return _store


def reset_store() -> None:
    global _store
    _store = None
