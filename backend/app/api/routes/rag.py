from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import RagQuery
from app.schemas import RagQueryOut
from app.services.reports import rag_totals

router = APIRouter(prefix="/rag", tags=["ai-rag"])


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    t = rag_totals(db)
    scores = [s for s in db.scalars(select(RagQuery.nli_score).order_by(RagQuery.ts.desc()).limit(200))]
    buckets = {"<0.80": 0, "0.80-0.90": 0, "0.90-0.95": 0, "0.95-0.98": 0, "≥0.98": 0}
    for s in scores:
        key = "<0.80" if s < 0.8 else "0.80-0.90" if s < 0.9 else "0.90-0.95" if s < 0.95 else "0.95-0.98" if s < 0.98 else "≥0.98"
        buckets[key] += 1
    return {**t, "distribution": [{"bucket": k, "count": v} for k, v in buckets.items()]}


@router.get("/queries", response_model=list[RagQueryOut])
def queries(db: Session = Depends(get_db), verdict: Literal["verified", "review"] | None = None, limit: int = Query(50, ge=1, le=200)) -> list[RagQuery]:
    q = select(RagQuery)
    if verdict:
        q = q.where(RagQuery.verdict == verdict)
    return list(db.scalars(q.order_by(RagQuery.ts.desc()).limit(limit)))


@router.get("/queries/{query_id}", response_model=RagQueryOut)
def query_detail(query_id: str, db: Session = Depends(get_db)) -> RagQuery:
    q = db.get(RagQuery, query_id)
    if q is None:  # also what a foreign tenant's id looks like: indistinguishable 404
        raise HTTPException(status_code=404, detail="Not found")
    return q
