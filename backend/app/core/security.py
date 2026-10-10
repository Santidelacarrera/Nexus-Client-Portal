"""Authentication & transport security: RS256 JWT, Argon2id, CSP/headers, rate limiting, auth middleware."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import get_settings
from app.core.keys import get_keyring
from app.core.store import get_store

# ---------------------------------------------------------------- password hashing (Argon2id)
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)  # argon2id by default
_DUMMY_HASH = _hasher.hash("nexus-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-ish time: always performs one Argon2 verification, even for unknown users."""
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------- JWT (RS256)
API_AUDIENCE = "nexus-api"
WS_AUDIENCE = "nexus-ws"


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str
    email: str
    jti: str
    auth_time: int = 0  # unix time of the original password login


def create_token(user_id: str, tenant_id: str, role: str, email: str, *, audience: str = API_AUDIENCE, ttl_seconds: int | None = None, auth_time: int | None = None) -> tuple[str, int]:
    s = get_settings()
    ttl = ttl_seconds or s.jwt_ttl_minutes * 60
    now = int(time.time())
    claims = {
        "iss": s.jwt_issuer,
        "aud": audience,
        "sub": user_id,
        "tid": tenant_id,
        "role": role,
        "email": email,
        "jti": uuid.uuid4().hex,
        "auth_time": auth_time or now,
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, get_keyring().jwt_private_pem, algorithm="RS256", headers={"typ": "JWT"}), ttl


def decode_token(token: str, audience: str = API_AUDIENCE) -> Principal:
    """Raises jwt.PyJWTError. Algorithm is pinned: 'none'/HS256 confusion is impossible."""
    c = jwt.decode(
        token,
        get_keyring().jwt_public_pem,
        algorithms=["RS256"],
        audience=audience,
        issuer=get_settings().jwt_issuer,
        options={"require": ["exp", "iat", "sub", "tid", "jti"]},
    )
    return Principal(c["sub"], c["tid"], c.get("role", "viewer"), c.get("email", ""), c["jti"], int(c.get("auth_time", c["iat"])))


# ---------------------------------------------------------------- client IP
def client_ip(request: Request) -> str:
    if get_settings().trusted_proxies:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- security headers / CSP (API)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """The API serves JSON only, so its CSP is maximally strict (no inline anything)."""

    HEADERS = {
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Cross-Origin-Resource-Policy": "same-site",
        "Cache-Control": "no-store",
    }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        response = await call_next(request)
        for k, v in self.HEADERS.items():
            response.headers.setdefault(k, v)
        if get_settings().is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        return response


# ---------------------------------------------------------------- rate limiting
def _too_many(retry_after: int, scope: str) -> JSONResponse:
    return JSONResponse(
        {"detail": f"Rate limit exceeded ({scope})"}, status_code=429, headers={"Retry-After": str(retry_after)}
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP limit for every request, with a much tighter bucket on the login endpoint."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        s = get_settings()
        store = get_store()
        ip = client_ip(request)
        minute = int(time.time() // 60)
        if request.url.path.endswith("/auth/login"):
            if await store.incr_window(f"rl:login:{ip}:{minute}", 60) > s.rate_limit_login_per_minute:
                return _too_many(60, "login")
        if await store.incr_window(f"rl:ip:{ip}:{minute}", 60) > s.rate_limit_ip_per_minute:
            return _too_many(60, "ip")
        return await call_next(request)


# ---------------------------------------------------------------- authentication middleware
PUBLIC_PATHS = {"/health", "/api/v1/auth/login", "/api/v1/reports/public-key", "/api/v1/webhooks/agents"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Rejects every /api request lacking a valid RS256 bearer token, then enforces the tenant bucket."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path
        if request.method == "OPTIONS" or path in PUBLIC_PATHS or not path.startswith("/api/"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        try:
            principal = decode_token(token)
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        if await get_store().exists(f"revoked:{principal.jti}"):
            return JSONResponse({"detail": "Session revoked"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        request.state.principal = principal
        minute = int(time.time() // 60)
        if await get_store().incr_window(f"rl:tenant:{principal.tenant_id}:{minute}", 60) > get_settings().rate_limit_tenant_per_minute:
            return _too_many(60, "tenant")
        return await call_next(request)
