"""Ingestion endpoint for Nexus agents (ShadowAPI_Guard …). Authenticated by per-tenant HMAC-SHA256."""
from __future__ import annotations

import json
import time

import anyio
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.core import crypto
from app.core.config import get_settings
from app.core.keys import get_keyring
from app.db.models import ApiFinding, Tenant
from app.db.session import tenant_session
from app.schemas import AgentWebhook, FindingOut
from app.services import bus
from app.services.audit import append_audit

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/agents", status_code=202)
async def agent_webhook(request: Request) -> dict:
    """Headers: X-Nexus-Tenant, X-Nexus-Timestamp (unix s), X-Nexus-Signature (sha256=hex of ts.body)."""
    body = await request.body()
    if len(body) > 64_000:
        raise HTTPException(413, "Payload too large")
    tenant_id = request.headers.get("x-nexus-tenant", "")
    ts = request.headers.get("x-nexus-timestamp", "")
    sig = request.headers.get("x-nexus-signature", "")
    try:
        skew = abs(time.time() - int(ts))
    except ValueError:
        raise HTTPException(401, "Invalid signature") from None
    key = crypto.webhook_key(get_keyring(), tenant_id)  # derivable for any id: unknown tenants simply fail below
    if skew > get_settings().webhook_max_skew_seconds or not crypto.verify_webhook(key, ts, body, sig):
        raise HTTPException(401, "Invalid signature")
    try:
        data = AgentWebhook.model_validate(json.loads(body))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "Invalid payload") from exc
    if data.tenant_id != tenant_id:
        raise HTTPException(401, "Invalid signature")

    def persist() -> dict:
        with tenant_session(tenant_id) as db:
            if db.get(Tenant, tenant_id) is None:  # RLS: unknown tenants simply have no visible row
                raise HTTPException(401, "Invalid signature")
            f = ApiFinding(tenant_id=tenant_id, **data.model_dump(exclude={"tenant_id"}))
            db.add(f)
            db.flush()
            append_audit(db, tenant_id, "webhook.finding.ingested", resource=f.id, meta={"category": f.category})
            db.commit()
            return FindingOut.model_validate(f).model_dump(mode="json")

    finding = await anyio.to_thread.run_sync(persist)
    await bus.publish(tenant_id, {"type": "finding", "data": finding})
    return {"accepted": True, "id": finding["id"]}
