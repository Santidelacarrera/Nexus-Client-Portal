from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, ip_of, require_roles
from app.core.security import Principal
from app.services.audit import append_audit
from app.db.models import ApiEndpoint, ApiFinding
from app.schemas import EndpointOut, FindingOut, FindingStatusUpdate
from app.services.reports import security_totals

router = APIRouter(prefix="/security", tags=["security"])

_SEV_ORDER = case({"critical": 0, "high": 1, "medium": 2, "low": 3}, value=ApiFinding.severity, else_=4)


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    by_cat = dict(db.execute(select(ApiFinding.category, func.count()).where(ApiFinding.status != "resolved").group_by(ApiFinding.category)).all())
    return {**security_totals(db), "by_category": by_cat}


@router.get("/findings", response_model=list[FindingOut])
def findings(
    db: Session = Depends(get_db),
    severity: Literal["critical", "high", "medium", "low"] | None = None,
    category: str | None = Query(None, max_length=40),
    status: Literal["open", "mitigating", "resolved"] | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[ApiFinding]:
    q = select(ApiFinding)
    if severity:
        q = q.where(ApiFinding.severity == severity)
    if category:
        q = q.where(ApiFinding.category == category)
    if status:
        q = q.where(ApiFinding.status == status)
    return list(db.scalars(q.order_by(_SEV_ORDER, ApiFinding.detected_at.desc()).limit(limit)))


@router.get("/endpoints", response_model=list[EndpointOut])
def endpoints(db: Session = Depends(get_db), status: Literal["documented", "shadow", "drift"] | None = None) -> list[ApiEndpoint]:
    q = select(ApiEndpoint)
    if status:
        q = q.where(ApiEndpoint.status == status)
    return list(db.scalars(q.order_by(ApiEndpoint.status, ApiEndpoint.calls_24h.desc()).limit(300)))


_CSV_COLS = ["id", "detected_at", "severity", "category", "status", "method", "endpoint", "cvss", "title", "source"]


def _csv_safe(v: object) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR) in exported cells."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/findings.csv")
def export_findings(request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_roles("owner", "analyst"))) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_COLS)
    for f in db.scalars(select(ApiFinding).order_by(_SEV_ORDER, ApiFinding.detected_at.desc()).limit(5000)):
        w.writerow([_csv_safe(getattr(f, c)) for c in _CSV_COLS])
    append_audit(db, p.tenant_id, "findings.export", user_id=p.user_id, ip=ip_of(request))
    db.commit()
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nexus-findings.csv"'})


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(finding_id: str, body: FindingStatusUpdate, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_roles("owner", "analyst"))) -> ApiFinding:
    f = db.get(ApiFinding, finding_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Not found")
    old, f.status = f.status, body.status
    append_audit(db, p.tenant_id, "finding.status_changed", user_id=p.user_id, resource=f.id, ip=ip_of(request), meta={"from": old, "to": body.status})
    db.commit()
    return f
