"""Notificación interna por correo al administrador cuando entra una consulta nueva.

Principios:
* OPCIONAL: sin SMTP_HOST o ADMIN_EMAIL no hace nada (solo una advertencia en el log).
* NUNCA rompe el flujo principal: se ejecuta DESPUÉS de guardar el mensaje y de responder al visitante (BackgroundTasks);
  cualquier fallo se captura y se registra sin credenciales ni contenido del mensaje.
* Credenciales solo por entorno (SMTP_PASSWORD es SecretStr). TLS verificado (certificado y nombre de host).
* El destinatario es exclusivamente ADMIN_EMAIL; el asunto no incluye datos del remitente (no hay inyección de cabeceras).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate
from typing import TYPE_CHECKING

from email_validator import EmailNotValidError, validate_email

if TYPE_CHECKING:  # solo para anotaciones
    from src.config import Settings

log = logging.getLogger("showcase.mail")
SMTP_TIMEOUT_SECONDS = 10
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _valid_address(value: str) -> bool:
    try:
        validate_email(value, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def is_enabled(settings: Settings) -> bool:
    return bool(settings.smtp_host.strip() and settings.admin_email.strip())


def build_message(settings: Settings, *, ref: str, name: str, email: str, message: str, received_at: datetime) -> EmailMessage:
    admin = settings.admin_email.strip()
    sender = settings.smtp_from.strip() or settings.smtp_user.strip() or admin
    msg = EmailMessage()
    msg["Subject"] = f"[Nexus] Nueva consulta {ref}"  # solo la referencia: nada del visitante en cabeceras
    msg["From"] = sender
    msg["To"] = admin  # exclusivamente el administrador
    msg["Date"] = formatdate()
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(
        "Notificación interna: llegó una nueva consulta por el formulario de contacto.\n"
        "\n"
        f"Referencia: {ref}\n"
        f"Recibida:   {received_at.isoformat(timespec='seconds')}\n"
        f"Nombre:     {name}\n"
        f"Correo:     {email}\n"
        "\n"
        "Contenido:\n"
        f"{message}\n"
        "\n"
        "--\n"
        "El registro oficial de esta consulta y la evidencia del consentimiento del titular (fecha, versión de la política\n"
        "y sesión) están resguardados en la base de datos interna, conforme a la Ley N.º 21.719. Este correo es solo un\n"
        "aviso: no lo reenvíes ni lo conserves fuera de los plazos de retención de la política de privacidad.\n",
        charset="utf-8", cte="quoted-printable",  # válido aunque el servidor no ofrezca 8BITMIME (si no, se corrompen las tildes)
    )
    return msg


def _send(settings: Settings, msg: EmailMessage) -> None:
    host, port, security = settings.smtp_host.strip(), settings.smtp_port, settings.smtp_security
    user = settings.smtp_user.strip()
    password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
    if user and password and security == "none" and host not in _LOCAL_HOSTS:
        raise RuntimeError("credenciales SMTP sin TLS rechazadas")  # nunca viajan en claro por la red
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)
    with client as smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def notify_new_message(settings: Settings, *, ref: str, name: str, email: str, message: str, received_at: datetime) -> bool:
    """Envía el aviso. Devuelve True si se envió. No lanza nunca: es una tarea de segundo plano."""
    try:
        if not is_enabled(settings):
            log.warning("Notificación por correo desactivada: faltan SMTP_HOST o ADMIN_EMAIL (ref=%s)", ref)
            return False
        if not _valid_address(settings.admin_email.strip()):
            log.warning("Notificación por correo omitida: ADMIN_EMAIL no es una dirección válida (ref=%s)", ref)
            return False
        _send(settings, build_message(settings, ref=ref, name=name, email=email, message=message, received_at=received_at))
        log.info("Notificación por correo enviada (ref=%s)", ref)
        return True
    except Exception as exc:  # noqa: BLE001 — por diseño nada de aquí debe afectar al servicio
        # Solo el tipo de error: el texto de la excepción puede traer usuario, servidor o fragmentos del mensaje.
        log.warning("Notificación por correo no enviada (ref=%s): %s", ref, type(exc).__name__)
        return False
