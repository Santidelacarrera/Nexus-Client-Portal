"""Service-to-service assertion: portal → MultiAgent_Consensus.

``base64url(payload).base64url(HMAC-SHA256(secret, base64url(payload)))``. It is the ONLY thing that establishes the
tenant for the downstream call: the body carries no tenant. ``bsha`` pins the assertion to the exact request body
(canonical JSON) and ``jti`` is single-use, so a captured assertion cannot be replayed or re-targeted.
Mirrors ``orchestrator/src/answer_gate/assertion.ts`` in MultiAgent_Consensus.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

ISSUER = "nexus-portal"
AUDIENCE = "multiagent-consensus"


def canonical_json(value: object) -> str:
    """Sorted keys, no whitespace, UTF-8 — byte-identical to the TypeScript ``canonicalJson``."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def body_hash(body: object) -> str:
    return hashlib.sha256(canonical_json(body).encode()).hexdigest()


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_assertion(secret: str, *, tenant_id: str, user_id: str, request_id: str, body: object, ttl: int = 60, now: float | None = None) -> str:
    t = int(now if now is not None else time.time())
    payload = {"iss": ISSUER, "aud": AUDIENCE, "tid": tenant_id, "sub": user_id, "rid": request_id, "jti": uuid.uuid4().hex,
               "iat": t, "exp": t + ttl, "bsha": body_hash(body)}
    p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    return f"{p}.{_b64u(hmac.new(secret.encode(), p.encode(), hashlib.sha256).digest())}"


def verify_assertion(header: str, secret: str, body: object, *, now: float | None = None) -> dict:
    """Reference verifier (used by tests as an executable spec of what the receiver enforces)."""
    p, _, sig = header.partition(".")
    expected = _b64u(hmac.new(secret.encode(), p.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise ValueError("bad signature")
    payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    t = now if now is not None else time.time()
    if payload["iss"] != ISSUER or payload["aud"] != AUDIENCE or payload["exp"] < t or payload["bsha"] != body_hash(body):
        raise ValueError("invalid assertion")
    return payload
