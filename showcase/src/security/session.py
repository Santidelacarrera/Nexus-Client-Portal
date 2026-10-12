"""Sesiones por JWT (PyJWT, HS256 = firmado HMAC) en cookies HttpOnly + Secure + SameSite=Strict.

* Visitante: identificador de sesión anónimo (solo sirve para enlazar la evidencia de consentimiento).
* Staff: sesión corta tras login con Argon2id.
Cada token lleva un valor CSRF; las peticiones que modifican estado deben devolverlo en `X-CSRF-Token`.
"""
from __future__ import annotations

import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request, Response

from src.config import Settings

ISSUER = "nexus-showcase"
AUD_VISITOR = "showcase-visitor"
AUD_STAFF = "showcase-staff"


@dataclass(frozen=True)
class Claims:
    sub: str
    csrf: str
    role: str


def issue(settings: Settings, *, audience: str, sub: str, role: str, ttl_seconds: int, csrf: str | None = None) -> tuple[str, str]:
    now = int(time.time())
    csrf = csrf or secrets.token_urlsafe(24)
    token = jwt.encode(
        {"iss": ISSUER, "aud": audience, "sub": sub, "role": role, "csrf": csrf, "iat": now, "nbf": now, "exp": now + ttl_seconds, "jti": uuid.uuid4().hex},
        settings.session_secret.get_secret_value(),
        algorithm="HS256",
    )
    return token, csrf


def read(settings: Settings, token: str | None, audience: str) -> Claims | None:
    if not token:
        return None
    try:
        c = jwt.decode(token, settings.session_secret.get_secret_value(), algorithms=["HS256"], audience=audience, issuer=ISSUER,
                       options={"require": ["exp", "iat", "sub", "csrf", "aud", "iss"]})
    except jwt.PyJWTError:
        return None
    return Claims(sub=c["sub"], csrf=c["csrf"], role=c.get("role", ""))


def set_cookie(response: Response, settings: Settings, name: str, token: str, ttl_seconds: int) -> None:
    response.set_cookie(name, token, max_age=ttl_seconds, path="/", httponly=True, secure=settings.cookie_secure, samesite="strict")


def check_csrf(request: Request, claims: Claims) -> None:
    given = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(given.encode(), claims.csrf.encode()):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")


def require_same_origin(request: Request, settings: Settings) -> None:
    """Defensa adicional contra CSRF: el Origin de toda petición que modifica estado debe ser un host permitido."""
    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(status_code=403, detail="Origen ausente")
    host = urlsplit(origin).hostname or ""
    if host not in settings.allowed_hosts:
        raise HTTPException(status_code=403, detail="Origen no permitido")
