"""Executive report generation, encryption-at-rest and cryptographic sign-off."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.keys import get_keyring
from app.db.models import ApiFinding, FinOpsSample, Report, RagQuery, Tenant, utcnow


def finops_totals(db: Session, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    base, actual, n = db.execute(
        select(func.coalesce(func.sum(FinOpsSample.baseline_cost), 0), func.coalesce(func.sum(FinOpsSample.actual_cost), 0), func.count())
        .where(FinOpsSample.ts >= since)
    ).one()
    saved = float(base) - float(actual)
    return {"baseline_usd": round(float(base), 2), "actual_usd": round(float(actual), 2), "saved_usd": round(saved, 2),
            "saving_pct": round(100 * saved / float(base), 1) if base else 0.0, "samples": int(n)}


def security_totals(db: Session) -> dict:
    rows = db.execute(select(ApiFinding.severity, ApiFinding.status, func.count()).group_by(ApiFinding.severity, ApiFinding.status)).all()
    out = {"open": {"critical": 0, "high": 0, "medium": 0, "low": 0}, "resolved": 0, "mitigating": 0}
    for sev, status, n in rows:
        if status == "open":
            out["open"][sev] = int(n)
        elif status in ("resolved", "mitigating"):
            out[status] += int(n)
    return out


def rag_totals(db: Session, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    n, avg = db.execute(select(func.count(), func.coalesce(func.avg(RagQuery.nli_score), 0)).where(RagQuery.ts >= since)).one()
    verified = db.scalar(select(func.count()).where(RagQuery.ts >= since, RagQuery.verdict == "verified")) or 0
    return {"queries": int(n), "avg_nli": round(float(avg), 4), "verified_pct": round(100 * verified / n, 1) if n else 0.0, "threshold": 0.95}


def consensus_votes(sec: dict, fin: dict, rag: dict) -> list[dict]:
    """MultiAgent_Consensus: each agent votes from its own evidence; no random numbers."""
    crit, high = sec["open"]["critical"], sec["open"]["high"]
    return [
        {"agent": "ShadowAPI_Guard", "vote": "reject" if crit else ("conditional" if high > 3 else "approve"), "evidence": f"{crit} critical / {high} high findings open"},
        {"agent": "KubeCost_Auto_HPA", "vote": "approve" if fin["saving_pct"] >= 10 else "conditional", "evidence": f"{fin['saving_pct']}% infrastructure saving over 30d"},
        {"agent": "ContextRAG_Engine", "vote": "approve" if rag["avg_nli"] >= 0.95 else "conditional", "evidence": f"mean NLI {rag['avg_nli']} (threshold 0.95)"},
    ]


def build_report(db: Session, tenant: Tenant, user_id: str, title: str | None = None) -> Report:
    ring, s = get_keyring(), get_settings()
    sec, fin, rag = security_totals(db), finops_totals(db), rag_totals(db)
    votes = consensus_votes(sec, fin, rag)
    score = sum({"approve": 1.0, "conditional": 0.5, "reject": 0.0}[v["vote"]] for v in votes) / len(votes)
    now = utcnow()
    body = {
        "tenant": {"id": tenant.id, "name": tenant.name},
        "period": {"from": (now - timedelta(days=30)).date().isoformat(), "to": now.date().isoformat()},
        "security": sec, "finops": fin, "ai_rag": rag,
        "multi_agent_consensus": {"votes": votes, "score": round(score, 3)},
        "generated_at": now.isoformat(),
    }
    plaintext = crypto.canonical_json(body)
    report = Report(
        tenant_id=tenant.id, title=title or f"Executive Report — {now:%B %Y}", period=f"{now:%Y-%m}",
        created_by=user_id, sha256=crypto.sha256_hex(plaintext), signature=crypto.sign_bytes(ring, plaintext),
        key_id=ring.report_key_id, signer=s.report_signer_name, consensus=round(score, 3), content_enc=b"",
    )
    db.add(report)
    db.flush()
    report.content_enc = crypto.encrypt_for_tenant(ring, tenant.id, plaintext, report.id)
    return report


def open_report(report: Report) -> bytes:
    return crypto.decrypt_for_tenant(get_keyring(), report.tenant_id, report.content_enc, report.id)


def bundle(report: Report) -> dict:
    ring = get_keyring()
    plaintext = open_report(report)
    return {
        "report": json.loads(plaintext),
        "integrity": {
            "algorithm": "RSA-PSS-SHA256", "sha256": report.sha256, "signature": report.signature,
            "key_id": report.key_id, "signer": report.signer, "public_key_pem": ring.report_public_pem,
            "canonicalization": "JSON, sorted keys, separators (',',':'), UTF-8",
        },
    }


def verify(report: Report) -> dict:
    ring = get_keyring()
    plaintext = open_report(report)
    digest_ok = crypto.sha256_hex(plaintext) == report.sha256
    sig_ok = crypto.verify_signature(ring.report_public_pem, plaintext, report.signature)
    return {"sha256_match": digest_ok, "signature_valid": sig_ok, "valid": digest_ok and sig_ok, "key_id": report.key_id, "signer": report.signer}
