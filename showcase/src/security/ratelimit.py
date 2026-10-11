"""Limitación de tasa con slowapi: mitiga fuerza bruta, scraping y spam del formulario."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from src.config import get_settings


def client_key(request: Request) -> str:
    """IP del cliente. X-Forwarded-For solo se respeta si TRUSTED_PROXY=true (proxy propio que lo sobrescribe)."""
    if get_settings().trusted_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def build_limiter(storage_uri: str) -> Limiter:
    return Limiter(key_func=client_key, default_limits=["120/minute"], storage_uri=storage_uri, headers_enabled=False)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:  # noqa: ARG001
    return JSONResponse({"detail": "Demasiadas solicitudes. Intenta de nuevo en un momento."}, status_code=429, headers={"Retry-After": "60"})
