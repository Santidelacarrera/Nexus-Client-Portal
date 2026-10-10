import json

from sqlalchemy import select, update

from app.core import crypto
from app.core.keys import get_keyring
from app.db.models import AuditLog, Report
from app.db.session import get_engine, system_session
from app.services.audit import verify_chain


def test_overview_and_domain_endpoints(client, acme):
    ov = client.get("/api/v1/overview", headers=acme["h"]).json()
    assert {s["key"] for s in ov["services"]} == {"security", "finops", "ai"}
    assert 0 <= ov["posture_score"] <= 100
    assert client.get("/api/v1/security/findings?severity=critical", headers=acme["h"]).status_code == 200
    assert client.get("/api/v1/security/findings?severity=bogus", headers=acme["h"]).status_code == 422
    fin = client.get("/api/v1/finops/summary", headers=acme["h"]).json()
    assert fin["saved_usd"] > 0 and fin["saving_pct"] > 0
    ts = client.get("/api/v1/finops/timeseries?days=3", headers=acme["h"]).json()
    assert ts and all(p["saved_usd"] >= 0 for p in ts)
    rag = client.get("/api/v1/rag/summary", headers=acme["h"]).json()
    assert 0.8 < rag["avg_nli"] <= 1


def test_rag_sources_have_coordinates_and_verdict_rule(client, acme):
    qs = client.get("/api/v1/rag/queries?limit=200", headers=acme["h"]).json()
    assert qs
    for q in qs:
        assert (q["nli_score"] >= 0.95) == (q["verdict"] == "verified")
        assert q["sources"] and all(s["line_end"] >= s["line_start"] and s["page"] >= 1 for s in q["sources"])


def test_rbac_viewer_cannot_generate_or_audit(client, acme_viewer):
    assert client.post("/api/v1/reports/generate", headers=acme_viewer["h"]).status_code == 403
    assert client.get("/api/v1/audit", headers=acme_viewer["h"]).status_code == 403
    assert client.get("/api/v1/reports", headers=acme_viewer["h"]).status_code == 200


def test_report_signature_and_encryption(client, acme):
    rep = client.post("/api/v1/reports/generate", headers=acme["h"])
    assert rep.status_code == 201
    rid = rep.json()["id"]
    dl = client.get(f"/api/v1/reports/{rid}/download", headers=acme["h"])
    assert dl.status_code == 200 and "attachment" in dl.headers["content-disposition"]
    b = json.loads(dl.text)
    pub = client.get("/api/v1/reports/public-key").text  # public, no auth
    canonical = crypto.canonical_json(b["report"])
    assert crypto.sha256_hex(canonical) == b["integrity"]["sha256"]
    assert crypto.verify_signature(pub, canonical, b["integrity"]["signature"])
    assert "Santiago de la Carrera" in b["integrity"]["signer"]
    tampered = dict(b["report"], finops={"saved_usd": 9e9})
    assert not crypto.verify_signature(pub, crypto.canonical_json(tampered), b["integrity"]["signature"])
    with system_session() as db:
        blob = db.get(Report, rid).content_enc
    assert acme["tenant"]["name"].encode() not in blob  # ciphertext at rest
    assert client.get(f"/api/v1/reports/{rid}/verify", headers=acme["h"]).json()["valid"] is True


def test_stored_report_tamper_is_detected(client, acme):
    rid = client.post("/api/v1/reports/generate", headers=acme["h"]).json()["id"]
    with system_session() as db:
        r = db.get(Report, rid)
        plain = crypto.canonical_json({"forged": True})
        r.content_enc = crypto.encrypt_for_tenant(get_keyring(), r.tenant_id, plain, r.id)
        db.commit()
    assert client.get(f"/api/v1/reports/{rid}/verify", headers=acme["h"]).json()["valid"] is False


def test_report_ciphertext_bound_to_tenant(client, acme, helix):
    import pytest
    from cryptography.exceptions import InvalidTag

    rid = client.post("/api/v1/reports/generate", headers=acme["h"]).json()["id"]
    with system_session() as db:
        blob = db.get(Report, rid).content_enc
    with pytest.raises(InvalidTag):
        crypto.decrypt_for_tenant(get_keyring(), helix["tenant"]["id"], blob, rid)


def test_audit_chain_valid_then_tamper_detected(client, acme):
    client.get("/api/v1/reports", headers=acme["h"])
    v = client.get("/api/v1/audit/verify", headers=acme["h"]).json()
    assert v["valid"] and v["entries"] > 2
    if get_engine().dialect.name == "postgresql":  # trigger + revoked grants forbid it outright
        import pytest
        from sqlalchemy.exc import DBAPIError

        with system_session() as db, pytest.raises(DBAPIError):
            db.execute(update(AuditLog).values(action="x"))
        return
    with system_session() as db:  # SQLite has no trigger; simulate an attacker with DB write access
        first = db.scalars(select(AuditLog).where(AuditLog.tenant_id == acme["tenant"]["id"]).order_by(AuditLog.id)).first()
        db.execute(update(AuditLog).where(AuditLog.id == first.id).values(action="nothing.to.see"))
        db.commit()
        assert verify_chain(db, acme["tenant"]["id"])["valid"] is False
        db.execute(update(AuditLog).where(AuditLog.id == first.id).values(action="tenant.seeded"))
        db.commit()
        assert verify_chain(db, acme["tenant"]["id"])["valid"] is True


def _hook(tenant_id, body: dict, *, ts=None, key_tenant=None, sig_override=None):
    import time

    raw = json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    sig = sig_override or crypto.sign_webhook(crypto.webhook_key(get_keyring(), key_tenant or tenant_id), ts, raw)
    return raw, {"X-Nexus-Tenant": tenant_id, "X-Nexus-Timestamp": ts, "X-Nexus-Signature": sig, "Content-Type": "application/json"}


PAYLOAD = dict(category="BOLA", severity="critical", method="GET", endpoint="/api/v2/accounts/{id}", title="hook finding", description="d", cvss=9.4)


def test_webhook_accepts_valid_hmac_and_streams(client, acme):
    tid = acme["tenant"]["id"]
    raw, h = _hook(tid, {**PAYLOAD, "tenant_id": tid})
    r = client.post("/api/v1/webhooks/agents", content=raw, headers=h)
    assert r.status_code == 202, r.text
    titles = [f["title"] for f in client.get("/api/v1/security/findings?severity=critical&limit=500", headers=acme["h"]).json()]
    assert "hook finding" in titles


def test_webhook_rejects_bad_signature_replay_and_cross_tenant(client, acme, helix):
    import time

    tid, other = acme["tenant"]["id"], helix["tenant"]["id"]
    body = {**PAYLOAD, "tenant_id": tid}
    raw, h = _hook(tid, body, sig_override="sha256=" + "0" * 64)
    assert client.post("/api/v1/webhooks/agents", content=raw, headers=h).status_code == 401
    raw, h = _hook(tid, body, ts=int(time.time()) - 3600)
    assert client.post("/api/v1/webhooks/agents", content=raw, headers=h).status_code == 401
    # signed with helix key but claiming acme
    raw, h = _hook(tid, body, key_tenant=other)
    assert client.post("/api/v1/webhooks/agents", content=raw, headers=h).status_code == 401
    # body tenant differs from signed header tenant
    raw, h = _hook(other, {**PAYLOAD, "tenant_id": tid})
    assert client.post("/api/v1/webhooks/agents", content=raw, headers=h).status_code == 401


def test_websocket_ticket_flow(client, acme):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    ticket = client.post("/api/v1/auth/ws-ticket", headers=acme["h"]).json()["ticket"]
    with client.websocket_connect(f"/ws/telemetry?ticket={ticket}", headers={"origin": "http://localhost:3000"}) as ws:
        assert ws.receive_json()["tenant_id"] == acme["tenant"]["id"]
    with pytest.raises(WebSocketDisconnect):  # replay of a consumed ticket
        with client.websocket_connect(f"/ws/telemetry?ticket={ticket}", headers={"origin": "http://localhost:3000"}):
            pass
    with pytest.raises(WebSocketDisconnect):  # API token is not a WS ticket
        with client.websocket_connect(f"/ws/telemetry?ticket={acme['access_token']}", headers={"origin": "http://localhost:3000"}):
            pass
    t2 = client.post("/api/v1/auth/ws-ticket", headers=acme["h"]).json()["ticket"]
    with pytest.raises(WebSocketDisconnect):  # foreign origin
        with client.websocket_connect(f"/ws/telemetry?ticket={t2}", headers={"origin": "https://evil.example"}):
            pass


def test_logout_revokes_token(client):
    from tests.conftest import _login

    d = _login(client, "analyst@acme-fintech.example")
    h = {"Authorization": f"Bearer {d['access_token']}"}
    assert client.get("/api/v1/overview", headers=h).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 204
    assert client.get("/api/v1/overview", headers=h).status_code == 401


def test_account_lockout_is_per_identity(client, settings):
    for _ in range(settings.login_max_failures):
        assert client.post("/api/v1/auth/login", json={"email": "victim@nowhere.example", "password": "x"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "victim@nowhere.example", "password": "x"})
    assert r.status_code == 429 and "retry-after" in r.headers
    # other identities are unaffected, and a real lockout also stops the correct password
    assert client.post("/api/v1/auth/login", json={"email": "ciso@acme-fintech.example", "password": "Test-Password-123!"}).status_code == 200
    for _ in range(settings.login_max_failures):
        client.post("/api/v1/auth/login", json={"email": "viewer@acme-fintech.example", "password": "bad"})
    assert client.post("/api/v1/auth/login", json={"email": "viewer@acme-fintech.example", "password": "Test-Password-123!"}).status_code == 429
    import anyio
    from app.core.store import get_store

    anyio.run(get_store().delete, "lock:viewer@acme-fintech.example")  # unlock for other tests


def test_finding_triage_workflow_and_audit(client, acme, acme_viewer, helix):
    f = client.get("/api/v1/security/findings?status=open&limit=1", headers=acme["h"]).json()[0]
    url = f"/api/v1/security/findings/{f['id']}"
    assert client.patch(url, json={"status": "resolved"}, headers=acme_viewer["h"]).status_code == 403
    assert client.patch(url, json={"status": "bogus"}, headers=acme["h"]).status_code == 422
    assert client.patch(url, json={"status": "resolved"}, headers=helix["h"]).status_code == 404  # cross-tenant
    r = client.patch(url, json={"status": "mitigating"}, headers=acme["h"])
    assert r.status_code == 200 and r.json()["status"] == "mitigating"
    log = client.get("/api/v1/audit?limit=20", headers=acme["h"]).json()
    assert any(e["action"] == "finding.status_changed" and e["resource"] == f["id"] for e in log)
    assert client.get("/api/v1/audit/verify", headers=acme["h"]).json()["valid"]


def test_csv_export_neutralises_formulas_and_is_role_gated(client, acme, acme_viewer):
    tid = acme["tenant"]["id"]
    raw, h = _hook(tid, {**PAYLOAD, "tenant_id": tid, "title": "=HYPERLINK(\"http://evil\")", "endpoint": "/csv-test"})
    assert client.post("/api/v1/webhooks/agents", content=raw, headers=h).status_code == 202
    assert client.get("/api/v1/security/findings.csv", headers=acme_viewer["h"]).status_code == 403
    r = client.get("/api/v1/security/findings.csv", headers=acme["h"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in r.text and ",=HYPERLINK" not in r.text
