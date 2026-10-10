from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_principal, ip_of
from app.core.security import WS_AUDIENCE, Principal, create_token, verify_password
from app.db.models import Tenant, User
from app.db.session import system_session
from app.schemas import LoginRequest, LoginResponse, TenantOut, UserOut, WsTicket
from app.services.audit import append_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    ip = ip_of(request)
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


@router.post("/ws-ticket", response_model=WsTicket)
def ws_ticket(principal: Principal = Depends(get_principal)) -> WsTicket:
    """Single-use, 30 s ticket so the long-lived bearer never appears in a WebSocket URL."""
    token, ttl = create_token(principal.user_id, principal.tenant_id, principal.role, principal.email, audience=WS_AUDIENCE, ttl_seconds=30)
    return WsTicket(ticket=token, expires_in=ttl)
