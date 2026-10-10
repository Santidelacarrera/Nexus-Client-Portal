"""SQLAlchemy 2.0 models. Every tenant-owned table carries ``tenant_id`` and is protected by
PostgreSQL Row-Level Security (see db/bootstrap.py) *and* by ORM-level scoping (db/session.py)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TenantScoped:
    """Mixin marking a table as tenant-owned (RLS + ORM criteria apply)."""

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True, nullable=False)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    plan: Mapped[str] = mapped_column(String(40), default="retainer-enterprise")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(TenantScoped, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # owner | analyst | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # TOTP MFA. Secret is AES-256-GCM encrypted with the tenant key; recovery codes stored as SHA-256.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mfa_recovery: Mapped[list] = mapped_column(JSON, default=list)
    mfa_last_counter: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), default=0)


class ApiEndpoint(TenantScoped, Base):
    """Inventory maintained by ShadowAPI_Guard."""

    __tablename__ = "api_endpoints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))  # documented | shadow | drift
    calls_24h: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiFinding(TenantScoped, Base):
    __tablename__ = "api_findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(40))  # BOLA | IDOR | Shadow API | Endpoint Drift | ...
    severity: Mapped[str] = mapped_column(String(10))  # critical | high | medium | low
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | mitigating | resolved
    method: Mapped[str] = mapped_column(String(8))
    endpoint: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    cvss: Mapped[float] = mapped_column(Float, default=0.0)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(40), default="ShadowAPI_Guard")


class FinOpsSample(TenantScoped, Base):
    """One hourly KubeCost_Auto_HPA sample for a cluster/namespace."""

    __tablename__ = "finops_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cluster: Mapped[str] = mapped_column(String(60))
    namespace: Mapped[str] = mapped_column(String(60))
    baseline_cost: Mapped[float] = mapped_column(Float)  # USD/h with static provisioning
    actual_cost: Mapped[float] = mapped_column(Float)  # USD/h after HPA right-sizing
    replicas_before: Mapped[int] = mapped_column(Integer)
    replicas_after: Mapped[int] = mapped_column(Integer)

    @property
    def saved(self) -> float:
        return round(self.baseline_cost - self.actual_cost, 4)


class RagQuery(TenantScoped, Base):
    __tablename__ = "rag_queries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    nli_score: Mapped[float] = mapped_column(Float)  # entailment index, 0..1
    verdict: Mapped[str] = mapped_column(String(12))  # verified (>=0.95) | review
    latency_ms: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(60))
    sources: Mapped[list["RagSource"]] = relationship(back_populates="query", cascade="all, delete-orphan", lazy="selectin")


class RagSource(TenantScoped, Base):
    __tablename__ = "rag_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    query_id: Mapped[str] = mapped_column(String(36), ForeignKey("rag_queries.id"), index=True)
    document: Mapped[str] = mapped_column(String(255))
    page: Mapped[int] = mapped_column(Integer)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    snippet: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column(Float)
    entailment: Mapped[float] = mapped_column(Float)
    query: Mapped[RagQuery] = relationship(back_populates="sources")


class Report(TenantScoped, Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    period: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(36))
    content_enc: Mapped[bytes] = mapped_column(LargeBinary)  # AES-256-GCM(nonce||ct||tag)
    sha256: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str] = mapped_column(Text)  # base64 RSA-PSS
    key_id: Mapped[str] = mapped_column(String(64))
    signer: Mapped[str] = mapped_column(String(160))
    consensus: Mapped[float] = mapped_column(Float, default=0.0)


class AuditLog(TenantScoped, Base):
    """Append-only, hash-chained per tenant. UPDATE/DELETE are blocked by trigger + grants."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_id", "tenant_id", "id"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


TENANT_TABLES = [m.__tablename__ for m in (User, ApiEndpoint, ApiFinding, FinOpsSample, RagQuery, RagSource, Report, AuditLog)]
