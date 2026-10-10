"""Live telemetry simulator for demos: persists new records and pushes them on the event bus."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

import anyio
from sqlalchemy import select

from app.db.models import Tenant
from app.db.session import system_session, tenant_session
from app.schemas import FindingOut, RagQueryOut
from app.services import bus
from app.services import generators as g
from app.services.reports import finops_totals

log = logging.getLogger("nexus.simulator")
_DOMAIN = {"acme-fintech": "fintech", "helix-health": "health"}


def _tick(tenant_id: str, slug: str, rng: random.Random) -> dict:
    domain = _DOMAIN.get(slug, "fintech")
    now = datetime.now(timezone.utc)
    roll = rng.random()
    with tenant_session(tenant_id) as db:
        if roll < 0.3:
            f = g.make_finding(rng, tenant_id, domain, now, status="open")
            db.add(f)
            db.commit()
            return {"type": "finding", "data": FindingOut.model_validate(f).model_dump(mode="json")}
        if roll < 0.6:
            cluster, namespaces = rng.choice(g.CLUSTERS)
            s = g.make_finops_sample(rng, tenant_id, now, cluster, rng.choice(namespaces))
            hourly_saved = s.saved
            # A live tick covers ~one interval, not a whole hour: persist prorated cost so the
            # current day is not inflated relative to the hourly seeded history.
            frac = 1 / 60
            s.baseline_cost, s.actual_cost = round(s.baseline_cost * frac, 4), round(s.actual_cost * frac, 4)
            db.add(s)
            db.commit()
            return {"type": "finops", "data": {"cluster": s.cluster, "namespace": s.namespace, "saved_usd": hourly_saved, "replicas_before": s.replicas_before, "replicas_after": s.replicas_after, "ts": now.isoformat(), "totals": finops_totals(db, 30)}}
        if roll < 0.85:
            q = g.make_rag_query(rng, tenant_id, domain, now)
            db.add(q)
            db.commit()
            return {"type": "rag", "data": RagQueryOut.model_validate(q).model_dump(mode="json")}
    return {"type": "heartbeat", "data": {"ts": now.isoformat()}}


def _tenants() -> list[tuple[str, str]]:
    with system_session() as db:
        return [(t.id, t.slug) for t in db.scalars(select(Tenant))]


async def run(interval: float) -> None:
    rng = random.Random()
    log.info("Telemetry simulator started (%.1fs)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            tenants = await anyio.to_thread.run_sync(_tenants)
            for tid, slug in tenants:
                event = await anyio.to_thread.run_sync(_tick, tid, slug, rng)
                await bus.publish(tid, event)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("simulator tick failed")
