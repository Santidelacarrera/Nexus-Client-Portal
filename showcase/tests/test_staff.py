import pytest

from tests.conftest import STAFF_PASSWORD, STAFF_USER, VALID




async def _login(c, password=STAFF_PASSWORD):
    return await c.post("/api/v1/staff/login", json={"username": STAFF_USER, "password": password})


async def test_staff_endpoints_need_auth(client):
    assert (await client.get("/api/v1/staff/mensajes")).status_code == 401


async def test_bad_credentials_rejected(client):
    assert (await _login(client, "incorrecta")).status_code == 401
    assert (await client.post("/api/v1/staff/login", json={"username": "otro", "password": STAFF_PASSWORD})).status_code == 401


async def test_visitor_cookie_cannot_be_used_as_staff(visitor):
    c, _ = visitor
    c.cookies.set("nx_staff", c.cookies.get("nx_sid"))  # audiencia distinta: no debe valer
    assert (await c.get("/api/v1/staff/mensajes")).status_code == 401


async def test_staff_flow_and_dto(visitor):
    c, csrf = visitor
    assert (await c.post("/api/v1/contacto", json=VALID, headers=csrf)).status_code == 201
    r = await _login(c)
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    staff_csrf = {"X-CSRF-Token": r.json()["csrf_token"]}
    msgs = (await c.get("/api/v1/staff/mensajes")).json()
    assert msgs and set(msgs[0]) == {"referencia", "nombre", "email", "mensaje", "estado", "recibido_en", "conservar_hasta", "consentimiento"}
    assert not {"id", "session_id", "consent_id"} & set(msgs[0])
    ref = msgs[0]["referencia"]
    assert (await c.post(f"/api/v1/staff/mensajes/{ref}/estado?estado=leido")).status_code == 403  # sin CSRF
    assert (await c.post(f"/api/v1/staff/mensajes/{ref}/estado?estado=leido", headers=staff_csrf)).status_code == 204
    assert (await c.post(f"/api/v1/staff/mensajes/{ref}/estado?estado=borrado", headers=staff_csrf)).status_code == 422
    assert (await c.post("/api/v1/staff/mensajes/NX-ZZZZZZZZ/estado?estado=leido", headers=staff_csrf)).status_code == 422


async def test_login_rate_limited(client):
    codes = [(await _login(client, "mala")).status_code for _ in range(7)]
    assert 429 in codes


async def test_password_hash_is_argon2id():
    from src.config import Settings

    assert Settings().staff_password_hash.get_secret_value().startswith("$argon2id$")
