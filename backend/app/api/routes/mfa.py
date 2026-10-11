"""TOTP multi-factor authentication: enrolment, challenge verification, disable."""
from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db, get_principal, ip_of
from app.core import crypto, totp
from app.core.config import get_settings
from app.core.keys import get_keyring
from app.core.security import MFA_AUDIENCE, Principal, create_token, decode_token
from app.core.store import get_store
from app.db.models import Tenant, User
from app.db.session import tenant_session
from app.schemas import LoginResponse, MfaCode, MfaEnabled, MfaSetup, MfaVerifyRequest, TenantOut, UserOut
from app.services.audit import append_audit

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])
LOCK_WINDOW = 900


def _aad(user: User) -> str:
    return f"mfa:{user.id}"


def _secret(user: User) -> str:
    return crypto.decrypt_for_tenant(get_keyring(), user.tenant_id, user.mfa_secret_enc, _aad(user)).decode()


def _check_code(user: User, code: str) -> bool:
    """TOTP (replay-protected via last used step) or a single-use recovery code."""
    if user.mfa_secret_enc:
        counter = totp.verify(_secret(user), code, last_counter=user.mfa_last_counter or 0)
        if counter is not None:
            user.mfa_last_counter = counter
            return True
    h = totp.hash_recovery(code)
    if h in (user.mfa_recovery or []):
        user.mfa_recovery = [x for x in user.mfa_recovery if x != h]  # burn it
        return True
    return False


@router.get("/status")
def status(p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, p.user_id)
    return {"enabled": bool(u and u.mfa_enabled), "recovery_codes_left": len(u.mfa_recovery or []) if u else 0}


@router.post("/setup", response_model=MfaSetup)
def setup(request: Request, p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> MfaSetup:
    u = db.get(User, p.user_id)
    if u.mfa_enabled:
        raise HTTPException(409, "MFA already enabled; disable it first")
    secret = totp.new_secret()
    u.mfa_secret_enc = crypto.encrypt_for_tenant(get_keyring(), u.tenant_id, secret.encode(), _aad(u))
    u.mfa_last_counter = 0
    append_audit(db, p.tenant_id, "mfa.setup_started", user_id=p.user_id, ip=ip_of(request))
    db.commit()
    return MfaSetup(secret=secret, uri=totp.provisioning_uri(secret, u.email))


@router.post("/enable", response_model=MfaEnabled)
def enable(body: MfaCode, request: Request, p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> MfaEnabled:
    u = db.get(User, p.user_id)
    if u.mfa_enabled or not u.mfa_secret_enc:
        raise HTTPException(409, "Start setup first")
    counter = totp.verify(_secret(u), body.code)
    if counter is None:
        raise HTTPException(422, "Invalid code")
    codes = totp.new_recovery_codes()
    u.mfa_enabled, u.mfa_last_counter = True, counter
    u.mfa_recovery = [totp.hash_recovery(c) for c in codes]
    append_audit(db, p.tenant_id, "mfa.enabled", user_id=p.user_id, ip=ip_of(request))
    db.commit()
    return MfaEnabled(recovery_codes=codes)  # shown exactly once


@router.post("/disable", status_code=204)
def disable(body: MfaCode, request: Request, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    from fastapi import Response

    u = db.get(User, p.user_id)
    if not u.mfa_enabled:
        raise HTTPException(409, "MFA is not enabled")
    ok = _check_code(u, body.code)
    append_audit(db, p.tenant_id, "mfa.disabled" if ok else "mfa.disable_failed", user_id=p.user_id, ip=ip_of(request))
    if ok:
        u.mfa_enabled, u.mfa_secret_enc, u.mfa_recovery, u.mfa_last_counter = False, None, [], 0
    db.commit()
    if not ok:
        raise HTTPException(422, "Invalid code")
    return Response(status_code=204)


@router.post("/verify", response_model=LoginResponse)
async def verify(body: MfaVerifyRequest, request: Request) -> LoginResponse:
    """Second login step. Failures count toward the same per-identity lockout as passwords."""
    try:
        claims = decode_token(body.mfa_token, audience=MFA_AUDIENCE)
    except jwt.PyJWTError:
        raise HTTPException(401, "Challenge expired; sign in again") from None
    store = get_store()
    key = f"lock:{claims.email.lower()}"
    if await store.count(key) >= get_settings().login_max_failures:
        raise HTTPException(429, "Too many failed attempts. Try again later.", headers={"Retry-After": str(LOCK_WINDOW)})
    used_key = f"mfa-challenge:{claims.jti}"
    if await store.exists(used_key):  # checked BEFORE verifying so a replay can never burn a recovery code
        raise HTTPException(401, "Challenge already used")
    result = await run_in_threadpool(_verify, claims, body.code, ip_of(request))
    if result is None:
        await store.incr_window(key, LOCK_WINDOW)
        raise HTTPException(401, "Invalid code")
    if not await store.set_once(used_key, 300):  # lost a race with a parallel verify of the same challenge
        raise HTTPException(401, "Challenge already used")
    await store.delete(key)
    return result


def _verify(claims: Principal, code: str, ip: str) -> LoginResponse | None:
    with tenant_session(claims.tenant_id) as db:
        u = db.get(User, claims.user_id)
        if u is None or not u.is_active or not u.mfa_enabled:
            return None
        ok = _check_code(u, code)
        append_audit(db, u.tenant_id, "auth.mfa.success" if ok else "auth.mfa.failure", user_id=u.id, ip=ip)
        db.commit()
        if not ok:
            return None
        tenant = db.get(Tenant, u.tenant_id)
        token, ttl = create_token(u.id, u.tenant_id, u.role, u.email)
        return LoginResponse(access_token=token, expires_in=ttl, user=UserOut.model_validate(u), tenant=TenantOut.model_validate(tenant))
