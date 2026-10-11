"""Client for MultiAgent_Consensus' answer gate (``POST /v1/answer-gate/reviews``).

Fail-closed by construction:
* transport problems, timeouts and upstream 4xx/5xx → ``ConsensusUnavailable`` (the user gets no answer);
* a body that is not EXACTLY ``answer-review.v1``, or that echoes another tenant/request/question →
  ``ContractViolation`` (a security event, not an error to paper over);
* ``enforce_invariants`` re-checks the committee rule locally: a RELEASED verdict is only honoured if all three agents
  approved with no blocking findings. The portal does not trust the upstream to have applied the protocol correctly.
"""
from __future__ import annotations

import logging

import httpx
from pydantic import ValidationError

from app.contracts.answer_review import AGENT_IDS, BLOCKING, AnswerReview, Reason
from app.core.service_assertion import make_assertion

log = logging.getLogger("nexus.consensus")


class ConsensusUnavailable(Exception):
    """The gate could not produce a verdict (network, timeout, 4xx/5xx)."""


class ContractViolation(Exception):
    """The gate answered, but not with a valid, tenant-consistent ``answer-review.v1``."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def enforce_invariants(review: AnswerReview) -> AnswerReview:
    """Defence in depth on top of the upstream's own protocol. Never *upgrades* a verdict, only downgrades."""
    if review.outcome == "BLOCKED":
        if review.answer is not None:  # a blocked verdict must never carry content
            review = review.model_copy(update={"answer": None})
        return review

    problems: list[str] = []
    by_agent = {v.agent: v for v in review.votes}
    if len(review.votes) != len(AGENT_IDS) or set(by_agent) != set(AGENT_IDS):
        problems.append("the panel is incomplete")
    for v in review.votes:
        if v.vote != "approve":
            problems.append(f"{v.agent} did not approve")
        if any(f.severity in BLOCKING for f in v.findings):
            problems.append(f"{v.agent} reported blocking findings")
    if not review.answer or not review.answer.strip():
        problems.append("no answer text")
    if review.reasons:
        problems.append("a released verdict lists blocking reasons")
    if not problems:
        return review
    log.error("RELEASED verdict violates the committee invariant tenant=%s request=%s: %s", review.tenantId, review.requestId, "; ".join(problems))
    reason = Reason(code="portal_invariant_violation", agent=None, severity="critical", detail="; ".join(problems))
    return review.model_copy(update={"outcome": "BLOCKED", "answer": None, "sources": [], "reasons": [reason, *review.reasons]})


class ConsensusClient:
    def __init__(self, base_url: str, secret: str, *, timeout: float = 20.0, transport: httpx.AsyncBaseTransport | None = None):
        self._url = base_url.rstrip("/") + "/v1/answer-gate/reviews"
        self._secret = secret
        self._timeout = timeout
        self._transport = transport

    async def review(self, *, tenant_id: str, user_id: str, request_id: str, question: str, top_k: int) -> AnswerReview:
        body = {"question": question, "topK": top_k}  # no tenant here: it travels only in the signed assertion
        headers = {
            "x-nexus-assertion": make_assertion(self._secret, tenant_id=tenant_id, user_id=user_id, request_id=request_id, body=body),
            "x-request-id": request_id,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                res = await http.post(self._url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ConsensusUnavailable(type(exc).__name__) from exc
        if res.status_code != 200:
            raise ConsensusUnavailable(f"upstream status {res.status_code}")
        try:
            review = AnswerReview.model_validate(res.json())
        except (ValueError, ValidationError) as exc:
            raise ContractViolation("schema_mismatch", "response is not answer-review.v1") from exc

        if review.tenantId != tenant_id:
            raise ContractViolation("tenant_mismatch", "response is bound to a different tenant")
        if review.requestId != request_id or review.question != question:
            raise ContractViolation("echo_mismatch", "response does not echo the request")
        return enforce_invariants(review)
