from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, ip_of, require_roles
from app.core.keys import get_keyring
from app.core.security import Principal
from app.db.models import Report, Tenant
from app.schemas import ReportOut
from app.services import reports as svc
from app.services.audit import append_audit

router = APIRouter(prefix="/reports", tags=["reports"])
_staff = require_roles("owner", "analyst")


@router.get("/public-key", response_class=PlainTextResponse)
def public_key() -> str:
    """Agency verification key — publishable so clients can verify reports offline."""
    return get_keyring().report_public_pem


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.created_at.desc()).limit(100)))


@router.post("/generate", response_model=ReportOut, status_code=201)
def generate(request: Request, db: Session = Depends(get_db), p: Principal = Depends(_staff)) -> Report:
    tenant = db.get(Tenant, p.tenant_id)
    report = svc.build_report(db, tenant, p.user_id)
    append_audit(db, p.tenant_id, "report.generate", user_id=p.user_id, resource=report.id, ip=ip_of(request), meta={"sha256": report.sha256})
    db.commit()
    return report


def _get(db: Session, report_id: str) -> Report:
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Not found")
    return r


@router.get("/{report_id}/download")
def download(report_id: str, request: Request, db: Session = Depends(get_db), p: Principal = Depends(_staff)) -> Response:
    report = _get(db, report_id)
    payload = json.dumps(svc.bundle(report), indent=2, ensure_ascii=False)
    append_audit(db, p.tenant_id, "report.download", user_id=p.user_id, resource=report.id, ip=ip_of(request))
    db.commit()
    return Response(payload, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="nexus-report-{report.period}-{report.id[:8]}.signed.json"'})


@router.get("/{report_id}/verify")
def verify(report_id: str, request: Request, db: Session = Depends(get_db), p: Principal = Depends(_staff)) -> dict:
    result = svc.verify(_get(db, report_id))
    append_audit(db, p.tenant_id, "report.verify", user_id=p.user_id, resource=report_id, ip=ip_of(request), meta={"valid": result["valid"]})
    db.commit()
    return result
