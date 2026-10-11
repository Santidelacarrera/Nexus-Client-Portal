"""Notificación opcional por correo: no debe afectar nunca al guardado, no debe filtrar credenciales y solo va al administrador."""
import logging
from datetime import datetime, timezone

import pytest

from src import mailer
from src.config import Settings, get_settings
from tests.conftest import VALID

PASSWORD = "s3cret-smtp-pw"
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
ARGS = dict(ref="NX-ABCD1234", name="Ana Pérez", email="ana@example.com", message="Necesito una cotización.\nGracias.", received_at=NOW)


def cfg(**kw) -> Settings:
    base = dict(smtp_host="smtp.test", admin_email="admin@example.test", smtp_user="mailer", smtp_password=PASSWORD)
    return Settings(**{**base, **kw})


class FakeSMTP:
    sent: list = []
    logins: list = []
    fail = False

    def __init__(self, host, port, **kw):
        if FakeSMTP.fail:
            raise OSError("boom " + PASSWORD)  # el texto del error NO debe llegar al log
        self.host, self.port = host, port

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): pass
    def login(self, user, password): FakeSMTP.logins.append((user, password))
    def send_message(self, msg): FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.logins, FakeSMTP.fail = [], [], False
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)


def test_disabled_without_config_warns_and_sends_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger="showcase.mail"):
        assert mailer.notify_new_message(cfg(smtp_host=""), **ARGS) is False
    assert not FakeSMTP.sent and "desactivada" in caplog.text


def test_message_goes_only_to_admin_with_basic_data_and_law_notice():
    assert mailer.notify_new_message(cfg(), **ARGS) is True
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "admin@example.test" and msg["Cc"] is None and msg["Bcc"] is None
    body = msg.get_content()
    for needle in ("Ana Pérez", "ana@example.com", "Necesito una cotización.", "NX-ABCD1234", "base de datos interna", "21.719"):
        assert needle in body
    assert "Ana" not in msg["Subject"] and "ana@" not in msg["Subject"]  # nada del visitante en cabeceras


def test_smtp_failure_never_raises_and_does_not_leak_credentials(caplog):
    FakeSMTP.fail = True
    with caplog.at_level(logging.WARNING, logger="showcase.mail"):
        assert mailer.notify_new_message(cfg(), **ARGS) is False
    assert "OSError" in caplog.text and PASSWORD not in caplog.text and "Ana" not in caplog.text


def test_invalid_admin_email_is_skipped_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="showcase.mail"):
        assert mailer.notify_new_message(cfg(admin_email="no-es-un-correo"), **ARGS) is False
    assert not FakeSMTP.sent and "no es una dirección válida" in caplog.text


def test_credentials_are_refused_without_tls_on_remote_hosts(caplog):
    with caplog.at_level(logging.WARNING, logger="showcase.mail"):
        assert mailer.notify_new_message(cfg(smtp_security="none"), **ARGS) is False
    assert not FakeSMTP.logins and PASSWORD not in caplog.text


def test_header_injection_is_impossible():
    evil = dict(ARGS, name="Ana\r\nBcc: atacante@example.com")
    assert mailer.notify_new_message(cfg(), **evil) is True  # el nombre solo va en el cuerpo
    assert FakeSMTP.sent[0]["Bcc"] is None


async def test_contact_is_saved_and_notified(app, visitor, admin_conn):
    app.dependency_overrides[get_settings] = lambda: cfg()
    try:
        c, csrf = visitor
        r = await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert r.status_code == 201
    assert len(FakeSMTP.sent) == 1 and r.json()["referencia"] in FakeSMTP.sent[0]["Subject"]
    assert await admin_conn.fetchval("SELECT count(*) FROM contact_messages WHERE email = $1", VALID["email"]) >= 1


async def test_contact_still_succeeds_when_smtp_is_down(app, visitor, admin_conn):
    FakeSMTP.fail = True
    app.dependency_overrides[get_settings] = lambda: cfg()
    try:
        c, csrf = visitor
        r = await c.post("/api/v1/contacto", json={**VALID, "email": "caida@example.com"}, headers=csrf)
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert r.status_code == 201  # el servicio no se rompe
    assert await admin_conn.fetchval("SELECT count(*) FROM contact_messages WHERE email = 'caida@example.com'") == 1
