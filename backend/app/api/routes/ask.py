"""``/api/v1/ask`` — question → ContextRAG retrieval → committee review (fail-closed) → answer + authorised sources.

The tenant is taken ONLY from the verified session. It is never read from the body (the schema forbids it), it
reaches MultiAgent_Consensus only inside a signed assertion, and every layer re-checks it on the way back.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db, get_principal, ip_of
from app.contracts.answer_review import AnswerReview, AskRequest, AskResult, AskRunSummary
from app.core import crypto
from app.core.config import get_settings
from app.core.keys import get_keyring
from app.core.security import Principal
from app.core.store import get_store
from app.db.models import ConsensusRun
from app.db.session import tenant_session
from app.services.audit import append_audit
from app.services.consensus_client import ConsensusClient, ConsensusUnavailable, ContractViolation

log = logging.getLogger("nexus.ask")
router = APIRouter(prefix="/ask", tags=["ask"])


def get_consensus_client() -> ConsensusClient:
    s = get_settings()
    secret = s.read_secret(s.consensus_assertion_secret, s.consensus_assertion_secret_path)
    if not s.consensus_url or not secret:
        raise HTTPException(status_code=503, detail="consensus_not_configured")
    if s.is_production and len(secret) < 32:
        raise HTTPException(status_code=503, detail="consensus_not_configured")
    return ConsensusClient(s.consensus_url, secret, timeout=s.consensus_timeout_seconds)


def _qhash(question: str) -> str:
    return hashlib.sha256(question.encode()).hexdigest()[:16]


def _persist(p: Principal, request_id: str, question: str, ip: str, *, review: AnswerReview | None, error: str | None, latency_ms: float) -> str:
    outcome = review.outcome if review else "ERROR"
    codes = [r.code for r in review.reasons] if review else ([error] if error else [])
    run_id = str(uuid.uuid4())
    payload = json.dumps({"question": question, "review": review.model_dump(mode="json") if review else None, "error": error}).encode()
    with tenant_session(p.tenant_id) as db:
        db.add(ConsensusRun(
            id=run_id, tenant_id=p.tenant_id, user_id=p.user_id, request_id=request_id, outcome=outcome, reason_codes=codes[:20],
            escalation=bool(review and review.escalation), latency_ms=latency_ms,
            payload_enc=crypto.encrypt_for_tenant(get_keyring(), p.tenant_id, payload, run_id),
        ))
        action = {"RELEASED": "ask.released", "BLOCKED": "ask.blocked"}.get(outcome, "ask.error")
        if error and error.startswith("contract:"):
            action = "ask.contract_violation"  # security-relevant: the upstream broke isolation or the schema
        # The question itself is never written to the (long-lived, immutable) audit trail: only a short digest.
        append_audit(db, p.tenant_id, action, user_id=p.user_id, resource=run_id, ip=ip, meta={"q": _qhash(question), "reasons": codes[:8], "request_id": request_id})
        db.commit()
    return run_id


@router.post("", response_model=AskResult)
async def ask(body: AskRequest, request: Request, p: Principal = Depends(get_principal), client: ConsensusClient = Depends(get_consensus_client)) -> AskResult:
    s = get_settings()
    minute = int(time.time() // 60)
    if await get_store().incr_window(f"rl:ask:{p.tenant_id}:{p.user_id}:{minute}", 60) > s.ask_rate_per_minute:
        raise HTTPException(status_code=429, detail="Too many questions. Try again in a minute.", headers={"Retry-After": "60"})

    request_id = uuid.uuid4().hex
    ip, t0 = ip_of(request), time.perf_counter()
    try:
        review = await client.review(tenant_id=p.tenant_id, user_id=p.user_id, request_id=request_id, question=body.question, top_k=body.topK)
    except ConsensusUnavailable as exc:
        log.warning("consensus unavailable tenant=%s request=%s: %s", p.tenant_id, request_id, exc)
        await run_in_threadpool(_persist, p, request_id, body.question, ip, review=None, error="consensus_unavailable", latency_ms=(time.perf_counter() - t0) * 1000)
        raise HTTPException(status_code=503, detail="consensus_unavailable", headers={"Retry-After": "5"}) from exc
    except ContractViolation as exc:
        log.error("CONTRACT VIOLATION tenant=%s request=%s code=%s", p.tenant_id, request_id, exc.code)
        await run_in_threadpool(_persist, p, request_id, body.question, ip, review=None, error=f"contract:{exc.code}", latency_ms=(time.perf_counter() - t0) * 1000)
        raise HTTPException(status_code=502, detail="consensus_contract_violation") from exc

    run_id = await run_in_threadpool(_persist, p, request_id, body.question, ip, review=review, error=None, latency_ms=(time.perf_counter() - t0) * 1000)
    return AskResult(runId=run_id, review=review)


def _open(run: ConsensusRun) -> dict:
    return json.loads(crypto.decrypt_for_tenant(get_keyring(), run.tenant_id, run.payload_enc, run.id))


@router.get("", response_model=list[AskRunSummary])
def history(db: Session = Depends(get_db), p: Principal = Depends(get_principal)) -> list[AskRunSummary]:
    runs = db.scalars(select(ConsensusRun).where(ConsensusRun.user_id == p.user_id).order_by(ConsensusRun.created_at.desc()).limit(25))
    return [AskRunSummary(runId=r.id, createdAt=r.created_at.isoformat(), question=_open(r)["question"], outcome=r.outcome, reasonCodes=r.reason_codes, escalation=r.escalation) for r in runs]


@router.get("/{run_id}", response_model=AskResult)
def detail(run_id: str, db: Session = Depends(get_db), p: Principal = Depends(get_principal)) -> AskResult:
    run = db.get(ConsensusRun, run_id)
    if run is None or run.user_id != p.user_id or run.outcome == "ERROR":  # users only see their own runs; foreign tenants → 404
        raise HTTPException(status_code=404, detail="Not found")
    return AskResult(runId=run.id, review=AnswerReview.model_validate(_open(run)["review"]))
