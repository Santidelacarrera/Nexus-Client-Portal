from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.db.models import AuditLog
from app.schemas import AuditOut
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_roles("owner"))])


@router.get("", response_model=list[AuditOut])
def entries(db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500)) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))


@router.get("/verify")
def verify(db: Session = Depends(get_db), p=Depends(require_roles("owner"))) -> dict:
    return verify_chain(db, p.tenant_id)
