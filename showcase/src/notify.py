"""Aviso por correo de una consulta nueva. Mejor esfuerzo: la consulta ya está guardada; un fallo de SMTP nunca la pierde.

* SMTP estándar (smtplib en un hilo), TLS por defecto. Credenciales solo desde el entorno.
* `EmailMessage` rechaza saltos de línea en cabeceras (sin inyección); el Asunto lleva solo la referencia.
* Los registros no incluyen datos personales: solo la referencia y el tipo de error.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from src.config import Settings

log = logging.getLogger("showcase.notify")


def enabled(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.contact_notify_to and settings.mail_from)


def build_message(settings: Settings, *, ref: str, name: str, email: str, message: str, policy_version: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = settings.contact_notify_to
    msg["Reply-To"] = email
    msg["Subject"] = f"Nueva consulta {ref} — Nexus Security & AI Lab"
    msg.set_content(
        f"Nueva consulta recibida en el sitio de Nexus Security & AI Lab.\n\n"
        f"Referencia: {ref}\nNombre: {name}\nCorreo: {email}\n"
        f"Consentimiento (Ley 21.719) registrado con la política: {policy_version}\n\n"
        f"Mensaje:\n{message}\n",
        charset="utf-8", cte="quoted-printable",  # válido aunque el servidor no ofrezca 8BITMIME
    )
    return msg


def _send(settings: Settings, msg: EmailMessage) -> None:
    timeout = settings.smtp_timeout_seconds
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout, context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        client.send_message(msg)


async def notify_contact(settings: Settings, *, ref: str, name: str, email: str, message: str, policy_version: str) -> bool:
    if not enabled(settings):
        return False
    try:
        msg = build_message(settings, ref=ref, name=name, email=email, message=message, policy_version=policy_version)
        await asyncio.to_thread(_send, settings, msg)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de red/SMTP se degrada a un aviso en el registro
        log.warning("contact notification failed ref=%s error=%s", ref, type(exc).__name__)
        return False
    log.info("contact notification sent ref=%s", ref)
    return True
