from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_principal, ip_of
from app.core.config import get_settings
from app.core.security import WS_AUDIENCE, Principal, create_token, verify_password
from app.core.store import get_store
from app.db.models import Tenant, User
from app.db.session import system_session
from app.schemas import LoginRequest, LoginResponse, TenantOut, UserOut, WsTicket
from app.services.audit import append_audit

router = APIRouter(prefix="/auth", tags=["auth"])


LOCK_WINDOW = 900  # seconds


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Per-account lockout (independent of IP): N failures in 15 min block that identity, known or not."""
    store, email = get_store(), body.email.lower().strip()
    key = f"lock:{email}"
    if await store.count(key) >= get_settings().login_max_failures:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.", headers={"Retry-After": str(LOCK_WINDOW)})
    try:
        result = await run_in_threadpool(_login, body, ip_of(request))
        await store.delete(key)
        return result
    except HTTPException as exc:
        if exc.status_code == 401:
            await store.incr_window(key, LOCK_WINDOW)
        raise


def _login(body: LoginRequest, ip: str) -> LoginResponse:
    with system_session() as db:  # tenant is unknown until the credentials resolve a user
        user = db.scalars(select(User).where(User.email == body.email.lower().strip())).first()
        ok = verify_password(user.password_hash if user else None, body.password) and bool(user and user.is_active)
        if user:
            append_audit(db, user.tenant_id, "auth.login.success" if ok else "auth.login.failure", user_id=user.id, ip=ip)
            db.commit()
        if not ok or user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        tenant = db.get(Tenant, user.tenant_id)
        token, ttl = create_token(user.id, user.tenant_id, user.role, user.email)
        return LoginResponse(access_token=token, expires_in=ttl, user=UserOut.model_validate(user), tenant=TenantOut.model_validate(tenant))


@router.get("/me", response_model=UserOut)
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> User:
    user = db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")
    return user


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, principal: Principal = Depends(get_principal)) -> Response:
    """Server-side revocation: the token's jti is denied for the rest of its lifetime."""
    await get_store().set_once(f"revoked:{principal.jti}", get_settings().jwt_ttl_minutes * 60)
    await run_in_threadpool(_audit_logout, principal, ip_of(request))
    return Response(status_code=204)


def _audit_logout(p: Principal, ip: str) -> None:
    from app.db.session import tenant_session

    with tenant_session(p.tenant_id) as db:
        append_audit(db, p.tenant_id, "auth.logout", user_id=p.user_id, ip=ip)
        db.commit()


@router.post("/ws-ticket", response_model=WsTicket)
def ws_ticket(principal: Principal = Depends(get_principal)) -> WsTicket:
    """Single-use, 30 s ticket so the long-lived bearer never appears in a WebSocket URL."""
    token, ttl = create_token(principal.user_id, principal.tenant_id, principal.role, principal.email, audience=WS_AUDIENCE, ttl_seconds=30)
    return WsTicket(ticket=token, expires_in=ttl)
