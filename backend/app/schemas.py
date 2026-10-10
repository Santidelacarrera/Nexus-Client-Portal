from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: str
    email: str
    full_name: str
    role: str
    tenant_id: str


class TenantOut(ORM):
    id: str
    name: str
    slug: str
    plan: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    tenant: TenantOut


class WsTicket(BaseModel):
    ticket: str
    expires_in: int


class FindingOut(ORM):
    id: str
    category: str
    severity: str
    status: str
    method: str
    endpoint: str
    title: str
    description: str
    evidence: dict
    cvss: float
    detected_at: datetime
    source: str


class EndpointOut(ORM):
    id: str
    method: str
    path: str
    status: str
    calls_24h: int
    last_seen: datetime


class RagSourceOut(ORM):
    id: str
    document: str
    page: int
    line_start: int
    line_end: int
    snippet: str
    similarity: float
    entailment: float


class RagQueryOut(ORM):
    id: str
    ts: datetime
    question: str
    answer: str
    nli_score: float
    verdict: str
    latency_ms: int
    model: str
    sources: list[RagSourceOut] = []


class ReportOut(ORM):
    id: str
    title: str
    period: str
    created_at: datetime
    sha256: str
    key_id: str
    signer: str
    consensus: float


class AuditOut(ORM):
    id: int
    ts: datetime
    user_id: str | None
    action: str
    resource: str | None
    ip: str | None
    prev_hash: str
    entry_hash: str


class AgentWebhook(BaseModel):
    tenant_id: str
    category: str = Field(max_length=40)
    severity: str = Field(pattern="^(critical|high|medium|low)$")
    method: str = Field(max_length=8)
    endpoint: str = Field(max_length=255)
    title: str = Field(max_length=200)
    description: str = Field(max_length=4000)
    cvss: float = Field(ge=0, le=10)
    evidence: dict = {}
