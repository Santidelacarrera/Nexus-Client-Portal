from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import FinOpsSample, utcnow
from app.services.reports import finops_totals

router = APIRouter(prefix="/finops", tags=["finops"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)) -> dict:
    t = finops_totals(db, days)
    t["projected_monthly_saving_usd"] = round(t["saved_usd"] / days * 30, 2)
    since = utcnow() - timedelta(days=days)
    rows = list(db.scalars(select(FinOpsSample).where(FinOpsSample.ts >= since)))
    by_cluster: dict[str, float] = defaultdict(float)
    by_ns: dict[str, float] = defaultdict(float)
    scale_events = 0
    for r in rows:
        by_cluster[r.cluster] += r.saved
        by_ns[f"{r.cluster}/{r.namespace}"] += r.saved
        scale_events += r.replicas_before != r.replicas_after
    t["hpa_scale_events"] = scale_events
    t["by_cluster"] = [{"cluster": k, "saved_usd": round(v, 2)} for k, v in sorted(by_cluster.items())]
    t["top_namespaces"] = [{"namespace": k, "saved_usd": round(v, 2)} for k, v in sorted(by_ns.items(), key=lambda kv: -kv[1])[:6]]
    return t


@router.get("/timeseries")
def timeseries(db: Session = Depends(get_db), days: int = Query(30, ge=1, le=90)) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    daily: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in db.scalars(select(FinOpsSample).where(FinOpsSample.ts >= since)):
        d = daily[r.ts.date().isoformat()]
        d[0] += r.baseline_cost
        d[1] += r.actual_cost
    return [
        {"date": k, "baseline_usd": round(v[0], 2), "actual_usd": round(v[1], 2), "saved_usd": round(v[0] - v[1], 2)}
        for k, v in sorted(daily.items())
    ]
