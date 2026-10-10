"""Immutable, hash-chained audit trail (per tenant)."""
from __future__ import annotations

import hashlib

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.crypto import canonical_json
from app.db.models import AuditLog, utcnow

GENESIS = "0" * 64


def _norm(ts: datetime) -> str:
    """Canonical UTC timestamp, stable across SQLite (naive) and PostgreSQL (aware)."""
    if ts.tzinfo:
        ts = ts.astimezone(timezone.utc)
    return ts.replace(tzinfo=None).isoformat()


def _digest(prev: str, tenant_id: str, ts: str, user_id: str | None, action: str, resource: str | None, ip: str | None, meta: dict) -> str:
    body = canonical_json([prev, tenant_id, ts, user_id, action, resource, ip, meta])
    return hashlib.sha256(body).hexdigest()


def append_audit(db: Session, tenant_id: str, action: str, *, user_id: str | None = None, resource: str | None = None, ip: str | None = None, meta: dict | None = None) -> AuditLog:
    """Append one entry. Caller commits. Serialised per-tenant so the chain cannot fork."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:t))"), {"t": tenant_id})
    last = db.scalars(
        select(AuditLog.entry_hash).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id.desc()).limit(1)
    ).first()
    prev = last or GENESIS
    ts = utcnow()
    meta = meta or {}
    entry = AuditLog(
        tenant_id=tenant_id, ts=ts, user_id=user_id, action=action, resource=resource, ip=ip, meta=meta,
        prev_hash=prev,
        entry_hash=_digest(prev, tenant_id, _norm(ts), user_id, action, resource, ip, meta),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, tenant_id: str) -> dict:
    prev = GENESIS
    count = 0
    for e in db.scalars(select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id)):
        ts = _norm(e.ts)
        expected = _digest(prev, tenant_id, ts, e.user_id, e.action, e.resource, e.ip, e.meta)
        if e.prev_hash != prev or e.entry_hash != expected:
            return {"valid": False, "entries": count, "broken_at": e.id}
        prev = e.entry_hash
        count += 1
    return {"valid": True, "entries": count, "broken_at": None, "head": prev}
