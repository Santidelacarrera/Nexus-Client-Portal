"""Correo de contacto con un servidor SMTP SIMULADO (socket local real; no sale nada a Internet)."""
import email
import socketserver
import threading
from email import policy

import pytest

from src.config import Settings, get_settings
from src.notify import build_message, enabled
from tests.conftest import VALID


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        w = lambda s: self.wfile.write((s + "\r\n").encode())  # noqa: E731
        w("220 stub ESMTP")
        data_mode, buf = False, []
        for raw in self.rfile:
            line = raw.decode(errors="replace").rstrip("\r\n")
            if data_mode:
                if line == ".":
                    self.server.messages.append("\n".join(buf))
                    data_mode, buf = False, []
                    w("250 queued")
                else:
                    buf.append(line[1:] if line.startswith("..") else line)
                continue
            cmd = line.upper()
            if cmd.startswith(("EHLO", "HELO")):
                w("250 stub")
            elif cmd.startswith(("MAIL", "RCPT", "RSET", "NOOP")):
                self.server.envelope.append(line); w("250 ok")
            elif cmd.startswith("DATA"):
                data_mode = True; w("354 go")
            elif cmd.startswith("QUIT"):
                w("221 bye"); return
            else:
                w("502 no")


@pytest.fixture
def smtp_stub():
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    srv.messages, srv.envelope = [], []
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown(); srv.server_close()


def _mail_settings(port: int, **kw) -> Settings:
    base = dict(smtp_host="127.0.0.1", smtp_port=port, smtp_security="none", mail_from="avisos@example.test",
                contact_notify_to="equipo@example.test", smtp_timeout_seconds=3)
    return Settings(**{**base, **kw})


def _use(app, settings):
    app.dependency_overrides[get_settings] = lambda: settings


async def test_contact_sends_mail_with_reference_and_reply_to(app, visitor, smtp_stub):
    c, csrf = visitor
    _use(app, _mail_settings(smtp_stub.server_address[1]))
    r = await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    assert r.status_code == 201
    assert len(smtp_stub.messages) == 1
    msg = email.message_from_string(smtp_stub.messages[0], policy=policy.default)
    ref = r.json()["referencia"]
    assert ref in msg["Subject"] and "Nexus Security & AI Lab" in msg["Subject"]
    assert msg["Reply-To"] == "ana@example.com" and msg["To"] == "equipo@example.test"
    body = msg.get_content()
    assert "Ana Pérez" in body and "Quiero conocer" in body and "Ley 21.719" in body
    assert any("equipo@example.test" in e for e in smtp_stub.envelope)


async def test_honeypot_and_invalid_send_no_mail(app, visitor, smtp_stub):
    c, csrf = visitor
    _use(app, _mail_settings(smtp_stub.server_address[1]))
    await c.post("/api/v1/contacto", json={**VALID, "website": "x"}, headers=csrf)
    await c.post("/api/v1/contacto", json={**VALID, "consentimiento_ley_21719": False}, headers=csrf)
    assert smtp_stub.messages == []


async def test_smtp_failure_never_loses_the_message(app, visitor, admin_conn):
    c, csrf = visitor
    _use(app, _mail_settings(1))  # puerto cerrado
    before = await admin_conn.fetchval("SELECT count(*) FROM contact_messages")
    r = await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    assert r.status_code == 201
    assert await admin_conn.fetchval("SELECT count(*) FROM contact_messages") == before + 1


async def test_disabled_without_configuration(app, visitor, smtp_stub):
    c, csrf = visitor
    _use(app, Settings())  # sin SMTP_HOST
    assert not enabled(Settings())
    assert (await c.post("/api/v1/contacto", json=VALID, headers=csrf)).status_code == 201
    assert smtp_stub.messages == []


def test_header_injection_is_rejected():
    s = _mail_settings(25)
    with pytest.raises(ValueError):
        build_message(s, ref="NX-1", name="x", email="a@b.co\r\nBcc: victima@example.org", message="m", policy_version="v")


async def test_logs_contain_no_personal_data(app, visitor, smtp_stub, caplog):
    import logging

    c, csrf = visitor
    _use(app, _mail_settings(1))
    with caplog.at_level(logging.INFO):
        await c.post("/api/v1/contacto", json=VALID, headers=csrf)
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "ana@example.com" not in logs and "Ana Pérez" not in logs and "Quiero conocer" not in logs
