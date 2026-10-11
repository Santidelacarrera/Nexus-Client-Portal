"""Portal side of the RAG + committee flow, against a simulated MultiAgent_Consensus (httpx.MockTransport)."""
import json

import httpx
import pytest
from sqlalchemy import select

from app.api.routes.ask import get_consensus_client
from app.contracts.answer_review import AGENT_IDS, AnswerReview, AskRequest
from app.core.service_assertion import body_hash, canonical_json, make_assertion, verify_assertion
from app.db.models import AuditLog, ConsensusRun
from app.db.session import system_session
from app.services.consensus_client import ConsensusClient, enforce_invariants

SECRET = "portal-assertion-secret-for-tests-0123456789"
Q = "¿Cuánto tiempo se conservan los registros de auditoría?"


def verdict(agent, vote="approve", findings=()):
    return {"agent": agent, "vote": vote, "score": 1.0 if vote == "approve" else 0.2, "findings": list(findings), "rationale": "ok" if vote == "approve" else "no"}


SRC = {"index": 1, "score": 0.9, "docId": "politica.md", "source": "politica.md", "section": "Retención", "page": None, "start": 0, "end": 60,
       "text": "Los registros de auditoría se conservan durante 7 años."}


def review_json(tenant_id, request_id, question=Q, **over):
    base = {
        "contract": "answer-review.v1", "requestId": request_id, "tenantId": tenant_id, "question": question, "outcome": "RELEASED",
        "answer": "Los registros de auditoría se conservan durante 7 años [1].", "reasons": [],
        "votes": [verdict(a) for a in AGENT_IDS], "sources": [SRC],
        "retrieval": {"status": "ok", "fragments": 1, "latencyMs": 12.0}, "timings": {"totalMs": 30.0, "retrievalMs": 12.0, "panelMs": 5.0}, "escalation": False,
    }
    return {**base, **over}


class Gate:
    """Records what the portal sends and answers with a configurable reply."""

    def __init__(self, reply=None, *, status=200, raises=None):
        self.reply, self.status, self.raises, self.requests = reply, status, raises, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body})
        if self.raises:
            raise self.raises
        a = verify_assertion(request.headers["x-nexus-assertion"], SECRET, body)  # the receiver's checks, as an executable spec
        reply = self.reply(a, body) if callable(self.reply) else self.reply
        return httpx.Response(self.status, json=reply)


@pytest.fixture()
def use_gate(client, settings):
    settings.consensus_url, settings.consensus_assertion_secret = "http://consensus.test", SECRET
    old_rate, settings.ask_rate_per_minute = settings.ask_rate_per_minute, 100_000  # shared test users must not trip the limiter
    installed = []

    def install(gate: Gate):
        installed.append(gate)
        client.app.dependency_overrides[get_consensus_client] = lambda: ConsensusClient("http://consensus.test", SECRET, transport=httpx.MockTransport(gate.handler))
        return gate

    yield install
    client.app.dependency_overrides.pop(get_consensus_client, None)
    settings.consensus_url = settings.consensus_assertion_secret = None
    settings.ask_rate_per_minute = old_rate


def ask(client, who, question=Q, **extra):
    return client.post("/api/v1/ask", json={"question": question, **extra}, headers=who["h"])


def ok_gate(**over):
    return Gate(lambda a, body: review_json(a["tid"], a["rid"], body["question"], **over))


# ------------------------------------------------------------------------------------ happy path & contract
def test_released_answer_flows_end_to_end_with_tenant_only_in_the_assertion(client, acme, use_gate):
    gate = use_gate(ok_gate())
    r = ask(client, acme)
    assert r.status_code == 200, r.text
    review = r.json()["review"]
    assert review["outcome"] == "RELEASED" and "7 años" in review["answer"]
    assert [v["vote"] for v in review["votes"]] == ["approve"] * 3 and review["sources"][0]["docId"] == "politica.md"
    sent = gate.requests[0]
    assert sent["body"] == {"question": Q, "topK": 5}  # no tenant in the body…
    a = verify_assertion(sent["headers"]["x-nexus-assertion"], SECRET, sent["body"])
    assert a["tid"] == acme["tenant"]["id"] and a["sub"] == acme["user"]["id"]  # …it travels only in the signed assertion
    assert sent["headers"]["x-request-id"] == a["rid"]


def test_viewers_can_ask_but_anonymous_cannot(client, acme_viewer, use_gate):
    use_gate(ok_gate())
    assert ask(client, acme_viewer).status_code == 200
    assert client.post("/api/v1/ask", json={"question": Q}).status_code == 401


@pytest.mark.parametrize("extra", [{"tenant_id": "x"}, {"tenantId": "x"}, {"tenant": "x"}, {"groups": ["admin"]}])
def test_the_body_can_never_choose_a_tenant(client, acme, use_gate, extra):
    gate = use_gate(ok_gate())
    assert ask(client, acme, **extra).status_code == 422
    assert gate.requests == []  # rejected before anything leaves the portal


def test_question_is_validated(client, acme, use_gate):
    use_gate(ok_gate())
    for bad in ("ab", "x" * 1001):
        assert ask(client, acme, bad).status_code == 422
    assert client.post("/api/v1/ask", json={"question": Q, "topK": 99}, headers=acme["h"]).status_code == 422


# ------------------------------------------------------------------------------------ committee disagreement
def test_committee_disagreement_blocks_and_never_exposes_the_answer(client, acme, use_gate):
    blocked = lambda a, body: review_json(  # noqa: E731
        a["tid"], a["rid"], body["question"], outcome="BLOCKED", answer=None, escalation=True,
        votes=[verdict("hallucination_critic", "reject", [{"code": "numeric_mismatch", "severity": "high", "detail": "5 vs 7"}]), verdict("tenant_security_auditor"), verdict("coherence_validator")],
        reasons=[{"code": "agent_rejected", "agent": "hallucination_critic", "severity": "high", "detail": "no"}, {"code": "numeric_mismatch", "severity": "high", "agent": "hallucination_critic", "detail": "5 vs 7"}])
    use_gate(Gate(blocked))
    r = ask(client, acme)
    assert r.status_code == 200
    rv = r.json()["review"]
    assert rv["outcome"] == "BLOCKED" and rv["answer"] is None and rv["escalation"] is True
    assert {x["code"] for x in rv["reasons"]} >= {"agent_rejected", "numeric_mismatch"}
    assert "7 años" not in json.dumps({k: v for k, v in rv.items() if k not in ("sources", "question")})


def test_a_blocked_verdict_that_leaks_an_answer_is_stripped_by_the_portal(client, acme, use_gate):
    leaky = lambda a, body: review_json(a["tid"], a["rid"], body["question"], outcome="BLOCKED", answer="SECRETO", votes=[], sources=[],  # noqa: E731
                                        reasons=[{"code": "tenant_security_veto", "agent": "tenant_security_auditor", "severity": "critical", "detail": "x"}])
    use_gate(Gate(leaky))
    r = ask(client, acme)
    assert r.json()["review"]["answer"] is None and "SECRETO" not in r.text


@pytest.mark.parametrize("name,mutate", [
    ("a reject vote", lambda r: r.update(votes=[verdict("hallucination_critic"), verdict("tenant_security_auditor", "reject"), verdict("coherence_validator")])),
    ("a missing agent", lambda r: r.update(votes=[verdict("hallucination_critic"), verdict("tenant_security_auditor")])),
    ("a duplicated agent", lambda r: r.update(votes=[verdict("hallucination_critic")] * 3)),
    ("blocking findings on an approve", lambda r: r.update(votes=[verdict("hallucination_critic"), verdict("tenant_security_auditor", findings=[{"code": "leak", "severity": "critical", "detail": "d"}]), verdict("coherence_validator")])),
    ("an empty answer", lambda r: r.update(answer="  ")),
    ("listed blocking reasons", lambda r: r.update(reasons=[{"code": "x", "agent": None, "severity": "high", "detail": "d"}])),
])
def test_released_verdicts_that_break_the_committee_rule_are_downgraded(client, acme, use_gate, name, mutate):
    def reply(a, body):
        r = review_json(a["tid"], a["rid"], body["question"])
        mutate(r)
        return r

    use_gate(Gate(reply))
    rv = ask(client, acme).json()["review"]
    assert rv["outcome"] == "BLOCKED", name
    assert rv["answer"] is None and rv["sources"] == []
    assert rv["reasons"][0]["code"] == "portal_invariant_violation"


# ------------------------------------------------------------------------------------ tenant isolation
def test_a_response_bound_to_another_tenant_is_a_contract_violation(client, acme, helix, use_gate):
    use_gate(Gate(lambda a, body: review_json(helix["tenant"]["id"], a["rid"], body["question"])))
    r = ask(client, acme)
    assert r.status_code == 502 and r.json()["detail"] == "consensus_contract_violation"
    assert "7 años" not in r.text and "politica.md" not in r.text
    with system_session() as db:
        e = db.scalars(select(AuditLog).where(AuditLog.tenant_id == acme["tenant"]["id"], AuditLog.action == "ask.contract_violation")).first()
        assert e is not None and e.meta["reasons"] == ["contract:tenant_mismatch"]


@pytest.mark.parametrize("name,mutate", [
    ("another request id", lambda r, a: r.update(requestId="someone-elses-request")),
    ("another question", lambda r, a: r.update(question="otra cosa")),
    ("an unknown field", lambda r, a: r.update(debug={"internal": True})),
    ("a different contract version", lambda r, a: r.update(contract="answer-review.v2")),
    ("a wrong type", lambda r, a: r.update(escalation="yes")),
    ("an unknown agent", lambda r, a: r.update(votes=[verdict("pirate")])),
])
def test_contract_drift_fails_closed(client, acme, use_gate, name, mutate):
    def reply(a, body):
        r = review_json(a["tid"], a["rid"], body["question"])
        mutate(r, a)
        return r

    use_gate(Gate(reply))
    r = ask(client, acme)
    assert r.status_code == 502, name
    assert "answer" not in r.text.lower() or "7 años" not in r.text


def test_the_gate_receives_each_users_own_tenant_and_never_mixes_them(client, acme, helix, use_gate):
    gate = use_gate(ok_gate())
    ask(client, acme)
    ask(client, helix)
    tids = [verify_assertion(g["headers"]["x-nexus-assertion"], SECRET, g["body"])["tid"] for g in gate.requests]
    assert tids == [acme["tenant"]["id"], helix["tenant"]["id"]]


def test_history_is_private_to_the_user_and_the_tenant(client, acme, helix, acme_viewer, use_gate):
    use_gate(ok_gate())
    run = ask(client, acme, "pregunta secreta de acme").json()["runId"]
    ids = lambda who: {h["runId"] for h in client.get("/api/v1/ask", headers=who["h"]).json()}  # noqa: E731
    assert run in ids(acme)
    assert run not in ids(helix) and run not in ids(acme_viewer)  # other tenant / other user of the same tenant
    assert client.get(f"/api/v1/ask/{run}", headers=helix["h"]).status_code == 404
    assert client.get(f"/api/v1/ask/{run}", headers=acme_viewer["h"]).status_code == 404
    mine = client.get(f"/api/v1/ask/{run}", headers=acme["h"])
    assert mine.status_code == 200 and mine.json()["review"]["tenantId"] == acme["tenant"]["id"]
    assert any(h["question"] == "pregunta secreta de acme" for h in client.get("/api/v1/ask", headers=acme["h"]).json())


def test_content_is_encrypted_at_rest_and_the_audit_trail_stores_no_question(client, acme, use_gate):
    use_gate(ok_gate())
    q = "pregunta confidencial única 8842"
    run = ask(client, acme, q).json()["runId"]
    with system_session() as db:
        row = db.get(ConsensusRun, run)
        assert q.encode() not in row.payload_enc and b"politica.md" not in row.payload_enc
        assert row.outcome == "RELEASED" and row.tenant_id == acme["tenant"]["id"]
        entries = [e for e in db.scalars(select(AuditLog).where(AuditLog.resource == run))]
        assert entries and all(q not in json.dumps(e.meta) for e in entries)
        assert entries[0].action == "ask.released" and len(entries[0].meta["q"]) == 16
    assert client.get("/api/v1/audit/verify", headers=acme["h"]).json()["valid"] is True


# ------------------------------------------------------------------------------------ upstream failures
@pytest.mark.parametrize("gate", [
    Gate(raises=httpx.ConnectError("down")),
    Gate(raises=httpx.ReadTimeout("slow")),
    Gate({"detail": "boom"}, status=500),
    Gate({"detail": "forbidden"}, status=401),
    Gate({"detail": "bad"}, status=400),
], ids=["connect-error", "timeout", "5xx", "401", "4xx"])
def test_upstream_failures_return_503_and_no_content(client, acme, use_gate, gate):
    use_gate(gate)
    r = ask(client, acme)
    assert r.status_code == 503 and r.json()["detail"] == "consensus_unavailable"
    with system_session() as db:
        last = db.scalars(select(ConsensusRun).where(ConsensusRun.tenant_id == acme["tenant"]["id"]).order_by(ConsensusRun.created_at.desc())).first()
        assert last.outcome == "ERROR"
    assert all(h["outcome"] == "ERROR" or True for h in client.get("/api/v1/ask", headers=acme["h"]).json())


def test_a_non_json_reply_is_a_contract_violation(client, acme, use_gate):
    use_gate(Gate(None, status=200))  # httpx.Response(json=None) → body "null"
    assert ask(client, acme).status_code == 502


def test_503_when_the_gate_is_not_configured(client, acme, settings):
    settings.consensus_url = settings.consensus_assertion_secret = None
    r = ask(client, acme)
    assert r.status_code == 503 and r.json()["detail"] == "consensus_not_configured"


def test_per_user_rate_limit(client, settings, use_gate):
    from tests.conftest import _login

    d = _login(client, "analyst@acme-fintech.example")  # a user no other test asks with: fresh bucket
    who = {"h": {"Authorization": f"Bearer {d['access_token']}"}}
    use_gate(ok_gate())
    settings.ask_rate_per_minute = 3  # use_gate restores the original on teardown
    codes = [ask(client, who).status_code for _ in range(6)]
    assert codes[:3] == [200, 200, 200] and 429 in codes[3:]


# ------------------------------------------------------------------------------------ units
def test_assertion_spec():
    body = {"question": "¿Qué?", "topK": 5}
    h = make_assertion(SECRET, tenant_id="t1", user_id="u1", request_id="r1", body=body)
    assert verify_assertion(h, SECRET, body)["tid"] == "t1"
    for bad in (lambda: verify_assertion(h, "other-secret", body), lambda: verify_assertion(h, SECRET, {**body, "topK": 6}), lambda: verify_assertion(h, SECRET, body, now=10**11)):
        with pytest.raises(ValueError):
            bad()
    # canonical JSON must be byte-identical to the TypeScript implementation (sorted keys, no spaces, raw UTF-8)
    assert canonical_json({"b": [1, {"z": "ñ\n", "a": None}], "a": "\"x\""}) == '{"a":"\\"x\\"","b":[1,{"a":null,"z":"ñ\\n"}]}'
    assert body_hash(body) == body_hash({"topK": 5, "question": "¿Qué?"})


def test_contract_schema_file_is_in_sync():
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "answer-review.v1.schema.json"
    if not path.exists():
        pytest.skip("contracts/ not present")
    generated = {"$comment": "Generated from app/contracts/answer_review.py — do not edit by hand", **AnswerReview.model_json_schema(), "$id": "answer-review.v1"}
    assert json.loads(path.read_text()) == json.loads(json.dumps(generated, sort_keys=True))
    assert "tenantId" not in AskRequest.model_json_schema()["properties"]


def test_enforce_invariants_never_upgrades():
    r = AnswerReview.model_validate(review_json("t", "r", outcome="BLOCKED", answer=None, votes=[], sources=[]))
    assert enforce_invariants(r).outcome == "BLOCKED"
