import re

import pytest

from tests.conftest import VALID




async def test_session_cookie_flags(client):
    r = await client.get("/api/v1/session")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert r.json()["policy_version"]


async def test_secure_cookie_prefix_in_production(monkeypatch):
    from src.config import Settings

    s = Settings(cookie_secure=True)
    assert s.visitor_cookie_name.startswith("__Host-")


async def test_contact_records_consent_evidence(visitor, admin_conn):
    c, csrf = visitor
    r = await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"estado", "referencia", "recibido_en"}  # DTO de salida mínimo
    assert re.fullmatch(r"NX-[0-9A-F]{8}", body["referencia"])
    row = await admin_conn.fetchrow(
        "SELECT m.email, m.status, m.retain_until > m.created_at AS retained, k.consent_key, k.policy_version, k.recorded_at, k.session_id "
        "FROM contact_messages m JOIN consent_records k ON k.id = m.consent_id ORDER BY m.created_at DESC LIMIT 1"
    )
    assert row["email"] == "ana@example.com" and row["status"] == "nuevo" and row["retained"]
    assert row["consent_key"] == "consentimiento_ley_21719"
    assert row["policy_version"] and row["recorded_at"] is not None and row["session_id"] is not None


async def test_requires_explicit_consent(visitor):
    c, csrf = visitor
    for bad in (False, None, "true", 1):
        payload = {**VALID, "consentimiento_ley_21719": bad}
        assert (await c.post("/api/v1/contacto", json=payload, headers=csrf)).status_code == 422
    payload = {k: v for k, v in VALID.items() if k != "consentimiento_ley_21719"}
    assert (await c.post("/api/v1/contacto", json=payload, headers=csrf)).status_code == 422


async def test_minimization_rejects_extra_fields(visitor):
    c, csrf = visitor
    r = await c.post("/api/v1/contacto", json={**VALID, "telefono": "+56 9 1234 5678"}, headers=csrf)
    assert r.status_code == 422


async def test_requires_session_csrf_and_origin(client, visitor):
    assert (await client.post("/api/v1/contacto", json=VALID)).status_code in (401, 403)  # sin sesión
    c, csrf = visitor
    assert (await c.post("/api/v1/contacto", json=VALID)).status_code == 403  # sin token CSRF
    assert (await c.post("/api/v1/contacto", json=VALID, headers={"X-CSRF-Token": "x" * 32})).status_code == 403
    assert (await c.post("/api/v1/contacto", json=VALID, headers={**csrf, "Origin": "https://evil.example"})).status_code == 403


async def test_html_is_stripped_and_stored_as_plain_text(visitor, admin_conn):
    c, csrf = visitor
    payload = {**VALID, "message": "Hola <script>alert(1)</script><img src=x onerror=alert(2)> necesito una demo", "name": "Luis <b>Díaz</b>"}
    r = await c.post("/api/v1/contacto", json=payload, headers=csrf)
    if r.status_code == 201:
        row = await admin_conn.fetchrow("SELECT name, message FROM contact_messages ORDER BY created_at DESC LIMIT 1")
        assert "<" not in row["message"] and "alert(1)" not in row["message"] and "onerror" not in row["message"]
        assert "<" not in row["name"]
    else:
        assert r.status_code == 422  # el nombre con etiquetas puede rechazarse: ambos desenlaces son seguros


async def test_honeypot_stores_nothing(visitor, admin_conn):
    c, csrf = visitor
    before = await admin_conn.fetchval("SELECT count(*) FROM contact_messages")
    r = await c.post("/api/v1/contacto", json={**VALID, "website": "http://spam.example"}, headers=csrf)
    assert r.status_code == 201
    assert await admin_conn.fetchval("SELECT count(*) FROM contact_messages") == before


async def test_contact_rate_limited(visitor):
    c, csrf = visitor
    codes = [(await c.post("/api/v1/contacto", json=VALID, headers=csrf)).status_code for _ in range(7)]
    assert codes[:5] == [201] * 5 and 429 in codes[5:]


async def test_forged_cookie_rejected(client):
    client.cookies.set("nx_sid", "no.es.un.jwt")
    assert (await client.post("/api/v1/contacto", json=VALID, headers={"X-CSRF-Token": "a"})).status_code == 401


async def test_expired_session_row_is_409(visitor, admin_conn):
    c, csrf = visitor
    await admin_conn.execute("TRUNCATE visitor_sessions CASCADE")
    r = await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    assert r.status_code == 409
