"""Real-time event bus per tenant: Redis Pub/Sub when available, else in-process fan-out."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator

from app.core.store import get_store

_local: dict[str, set[asyncio.Queue]] = defaultdict(set)


def channel(tenant_id: str) -> str:
    return f"telemetry:{tenant_id}"


async def publish(tenant_id: str, event: dict) -> None:
    payload = json.dumps(event, default=str)
    redis = get_store().redis
    if redis:
        try:
            await redis.publish(channel(tenant_id), payload)
            return
        except Exception:  # noqa: BLE001
            pass
    for q in list(_local[tenant_id]):
        if q.full():
            q.get_nowait()  # drop oldest: slow consumers must not block producers
        q.put_nowait(payload)


async def subscribe(tenant_id: str) -> AsyncIterator[dict]:
    """Yield events for exactly one tenant — the channel name is derived from the verified claim."""
    redis = get_store().redis
    if redis:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel(tenant_id))
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    yield json.loads(msg["data"])
        finally:
            await pubsub.unsubscribe(channel(tenant_id))
            await pubsub.aclose()
    else:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        _local[tenant_id].add(q)
        try:
            while True:
                yield json.loads(await q.get())
        finally:
            _local[tenant_id].discard(q)
