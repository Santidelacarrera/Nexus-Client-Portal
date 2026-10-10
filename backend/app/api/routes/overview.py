from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_principal
from app.core.security import Principal
from app.db.models import ApiEndpoint, ApiFinding, Tenant, utcnow
from app.services import reports as svc

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
def overview(db: Session = Depends(get_db), p: Principal = Depends(get_principal)) -> dict:
    sec, fin, rag = svc.security_totals(db), svc.finops_totals(db), svc.rag_totals(db)
    tenant = db.get(Tenant, p.tenant_id)
    endpoints = dict(db.execute(select(ApiEndpoint.status, func.count()).group_by(ApiEndpoint.status)).all())
    last24 = db.scalar(select(func.count()).where(ApiFinding.detected_at >= utcnow() - timedelta(hours=24))) or 0
    open_total = sum(sec["open"].values())
    penalty = sec["open"]["critical"] * 15 + sec["open"]["high"] * 6 + sec["open"]["medium"] * 2 + sec["open"]["low"]
    posture = round(100 / (1 + penalty / 60))  # smooth 100→0: never saturates at 0 for a large backlog
    votes = svc.consensus_votes(sec, fin, rag)
    return {
        "tenant": {"name": tenant.name, "plan": tenant.plan},
        "services": [
            {"key": "security", "name": "ShadowAPI_Guard", "status": "degraded" if sec["open"]["critical"] else "operational", "headline": f"{open_total} open findings", "detail": f"{last24} new in 24h"},
            {"key": "finops", "name": "KubeCost_Auto_HPA", "status": "operational", "headline": f"${fin['saved_usd']:,.0f} saved (30d)", "detail": f"{fin['saving_pct']}% vs static provisioning"},
            {"key": "ai", "name": "ContextRAG_Engine", "status": "operational" if rag["avg_nli"] >= 0.95 else "degraded", "headline": f"NLI {rag['avg_nli']:.3f}", "detail": f"{rag['verified_pct']}% answers ≥ 0.95"},
        ],
        "security": sec, "finops": fin, "ai_rag": rag, "endpoints": endpoints,
        "posture_score": posture, "consensus": votes,
    }
