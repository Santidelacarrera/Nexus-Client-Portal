import time

import anyio

from app.core import totp
from app.core.security import password_problem
from app.core.store import get_store
from tests.conftest import PASSWORD, _login


def _bearer(d):
    return {"Authorization": f"Bearer {d['access_token']}"}


def test_password_policy_unit():
    assert password_problem("short1!", "a@b.example")
    assert password_problem("password12345", "a@b.example")
    assert password_problem("santiago-secure-1", "santiago@x.example")  # contains email name
    assert password_problem("aaaaaaaaaaaaaaaa", "a@b.example")
    assert password_problem("correct-Horse-battery-9", "a@b.example") is None


def _reset_password(email: str) -> None:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.models import User
    from app.db.session import system_session

    with system_session() as db:
        db.scalars(select(User).where(User.email == email)).first().password_hash = hash_password(PASSWORD)
        db.commit()
    anyio.run(get_store().delete, f"lock:{email}")
    anyio.run(get_store().delete, f"sessions-valid-after:{_uid(email)}")


def _uid(email: str) -> str:
    from sqlalchemy import select

    from app.db.models import User
    from app.db.session import system_session

    with system_session() as db:
        return db.scalars(select(User.id).where(User.email == email)).first()


def test_change_password_revokes_sessions_and_enforces_policy(client):
    email, new = "analyst@acme-fintech.example", "Another-Strong-Pass-77"
    s1, s2 = _login(client, email), _login(client, email)
    h = _bearer(s1)
    url = "/api/v1/auth/password"
    try:
        assert client.post(url, json={"current_password": PASSWORD, "new_password": "short"}, headers=h).status_code == 422
        assert client.post(url, json={"current_password": PASSWORD, "new_password": PASSWORD}, headers=h).status_code == 422
        assert client.post(url, json={"current_password": "wrong", "new_password": new}, headers=h).status_code == 401
        assert client.post(url, json={"current_password": PASSWORD, "new_password": new}, headers=h).status_code == 204
        # every pre-existing session dies, including other devices
        assert client.get("/api/v1/overview", headers=h).status_code == 401
        assert client.get("/api/v1/overview", headers=_bearer(s2)).status_code == 401
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
        d = client.post("/api/v1/auth/login", json={"email": email, "password": new}).json()
        assert client.get("/api/v1/overview", headers=_bearer(d)).status_code == 200  # new session works
    finally:
        _reset_password(email)


def test_wrong_current_password_feeds_lockout(client, settings):
    email = "viewer@helix-health.example"
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "x"}).status_code == 401  # unknown user ok
    d = _login(client, "analyst@helix-health.example")
    h = _bearer(d)
    for _ in range(settings.login_max_failures):
        client.post("/api/v1/auth/password", json={"current_password": "bad", "new_password": "Whatever-Long-Pass-1"}, headers=h)
    assert client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "Whatever-Long-Pass-1"}, headers=h).status_code == 429
    anyio.run(get_store().delete, "lock:analyst@helix-health.example")


def test_logout_all_kills_every_session(client):
    email = "analyst@acme-fintech.example"
    a, b = _login(client, email), _login(client, email)
    assert client.post("/api/v1/auth/logout-all", headers=_bearer(a)).status_code == 204
    assert client.get("/api/v1/overview", headers=_bearer(a)).status_code == 401
    assert client.get("/api/v1/overview", headers=_bearer(b)).status_code == 401
    time.sleep(0.01)
    assert client.get("/api/v1/overview", headers=_bearer(_login(client, email))).status_code == 200


def test_mfa_required_role_is_confined_until_enrolled(client, settings):
    settings.mfa_required_roles = ["owner"]
    try:
        d = _login(client, "ciso@helix-health.example")
        h = _bearer(d)
        r = client.get("/api/v1/overview", headers=h)
        assert r.status_code == 403 and r.json()["code"] == "mfa_enrollment_required"
        assert client.post("/api/v1/auth/ws-ticket", headers=h).status_code == 403
        me = client.get("/api/v1/auth/me", headers=h).json()
        assert me["mfa_setup_required"] is True and me["tenant_name"] == "Helix Health"

        secret = client.post("/api/v1/auth/mfa/setup", headers=h).json()["secret"]
        code = totp.hotp(secret, int(time.time() // 30))
        assert client.post("/api/v1/auth/mfa/enable", json={"code": code}, headers=h).status_code == 200
        assert client.get("/api/v1/overview", headers=h).status_code == 403  # old token still confined...
        fresh = client.post("/api/v1/auth/refresh", headers=h).json()  # ...until it is refreshed
        assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {fresh['access_token']}"}).status_code == 200
        # non-required roles are never confined
        assert client.get("/api/v1/overview", headers=_bearer(_login(client, "analyst@helix-health.example"))).status_code == 200
        # cleanup: disable MFA with a fresh code
        nxt = totp.hotp(secret, int(time.time() // 30) + 1)
        assert client.post("/api/v1/auth/mfa/disable", json={"code": nxt}, headers={"Authorization": f"Bearer {fresh['access_token']}"}).status_code == 204
    finally:
        settings.mfa_required_roles = []


def test_metrics_endpoint_is_off_unless_token_set(client, settings):
    assert client.get("/metrics").status_code == 404
    settings.metrics_token = "metrics-secret-token"
    try:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401
        r = client.get("/metrics", headers={"Authorization": "Bearer metrics-secret-token"})
        assert r.status_code == 200
        assert "nexus_http_requests_total" in r.text and "nexus_audit_events_total" in r.text
        assert 'route="/api/v1/overview"' in r.text  # templated routes, not raw ids
    finally:
        settings.metrics_token = None


def test_request_id_propagation_and_sanitising(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-12345678"})
    assert r.headers["x-request-id"] == "trace-12345678"
    evil = client.get("/health", headers={"X-Request-ID": "x\nforged-log-line"})
    assert evil.headers["x-request-id"] != "x\nforged-log-line" and len(evil.headers["x-request-id"]) == 32
