"""Contract ``answer-review.v1`` — portal ⇄ MultiAgent_Consensus (which in turn calls ContextRAG).

Field names are camelCase on purpose: they are the wire format shared with the TypeScript orchestrator.
Every model forbids unknown fields. A response that does not match EXACTLY is treated as a contract
violation and fails closed — a silent drift between services must never degrade into "best effort".
JSON Schema: ``contracts/answer-review.v1.schema.json`` (regenerate with ``python -m app.contracts.answer_review``).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "answer-review.v1"
AgentId = Literal["hallucination_critic", "tenant_security_auditor", "coherence_validator"]
AGENT_IDS: tuple[str, ...] = ("hallucination_critic", "tenant_security_auditor", "coherence_validator")
Severity = Literal["info", "low", "medium", "high", "critical"]
BLOCKING = {"high", "critical"}


class Strict(BaseModel):
    # strict: no "yes"→True / "5"→5 coercions. The wire format must match exactly or the call fails closed.
    model_config = ConfigDict(extra="forbid", strict=True)


class AskRequest(Strict):
    """What a user may send. There is deliberately NO tenant field: the tenant comes from the verified session."""

    question: str = Field(min_length=3, max_length=1000)
    topK: int = Field(5, ge=1, le=10)


class Finding(Strict):
    code: str
    severity: Severity
    detail: str
    fragmentIndex: int | None = None


class Verdict(Strict):
    agent: AgentId
    vote: Literal["approve", "reject"]
    score: float = Field(ge=0, le=1)
    findings: list[Finding]
    rationale: str


class Reason(Strict):
    code: str
    agent: AgentId | None
    severity: Severity
    detail: str


class Source(Strict):
    index: int
    score: float
    docId: str
    source: str
    section: str
    page: int | None
    start: int
    end: int
    text: str


class Retrieval(Strict):
    status: Literal["ok", "no_results", "unavailable"]
    fragments: int
    latencyMs: float


class Timings(Strict):
    totalMs: float
    retrievalMs: float
    panelMs: float


class AnswerReview(Strict):
    contract: Literal["answer-review.v1"]
    requestId: str
    tenantId: str
    question: str
    outcome: Literal["RELEASED", "BLOCKED"]
    answer: str | None
    reasons: list[Reason]
    votes: list[Verdict]
    sources: list[Source]
    retrieval: Retrieval
    timings: Timings
    escalation: bool


class AskResult(Strict):
    """What the portal returns to the browser."""

    runId: str
    review: AnswerReview


class AskRunSummary(Strict):
    runId: str
    createdAt: str
    question: str
    outcome: Literal["RELEASED", "BLOCKED", "ERROR"]
    reasonCodes: list[str]
    escalation: bool


def write_schema(path: str) -> None:
    import json

    schema = {"$comment": "Generated from app/contracts/answer_review.py — do not edit by hand", **AnswerReview.model_json_schema()}
    schema["$id"] = CONTRACT_VERSION
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    import sys

    write_schema(sys.argv[1] if len(sys.argv) > 1 else "../contracts/answer-review.v1.schema.json")
