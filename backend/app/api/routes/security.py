from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import ApiEndpoint, ApiFinding
from app.schemas import EndpointOut, FindingOut
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
