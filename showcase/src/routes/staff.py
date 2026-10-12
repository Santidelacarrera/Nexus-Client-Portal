"""Panel interno de lectura de mensajes. Autenticación Argon2id + sesión corta; usa un ROL DE BASE DE DATOS distinto."""


from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src import db
from src.config import Settings, get_settings
from src.deps import require_staff, staff_sessionmaker
from src.routes.api import limiter
from src.schemas import ConsentOut, StaffLoginIn, StaffMessageOut, StaffSessionOut
from src.security import session as sess
from src.security.passwords import verify_staff

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


@router.post("/login", response_model=StaffSessionOut)
@limiter.limit("5/minute")
async def login(body: StaffLoginIn, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> StaffSessionOut:
    sess.require_same_origin(request, settings)
    hash_ = settings.staff_password_hash.get_secret_value() if settings.staff_password_hash else None
    if not verify_staff(body.username, body.password, settings.staff_username, hash_):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    ttl = settings.staff_session_minutes * 60
    token, csrf = sess.issue(settings, audience=sess.AUD_STAFF, sub="staff", role="staff", ttl_seconds=ttl)
    sess.set_cookie(response, settings, settings.staff_cookie_name, token, ttl)
    return StaffSessionOut(csrf_token=csrf)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, settings: Settings = Depends(get_settings), claims: sess.Claims = Depends(require_staff)) -> Response:
    sess.require_same_origin(request, settings)
    sess.check_csrf(request, claims)
    response.delete_cookie(settings.staff_cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="strict")
    response.status_code = 204
    return response


@router.get("/mensajes", response_model=list[StaffMessageOut])
@limiter.limit("30/minute")
async def mensajes(request: Request, _: sess.Claims = Depends(require_staff)) -> list[StaffMessageOut]:
    rows = await db.list_messages(staff_sessionmaker(request))
    return [
        StaffMessageOut(
            referencia="NX-" + m.id.hex[:8].upper(), nombre=m.name, email=m.email, mensaje=m.message, estado=m.status,  # type: ignore[arg-type]
            recibido_en=m.created_at, conservar_hasta=m.retain_until, consentimiento=ConsentOut(version=c.policy_version, registrado_en=c.recorded_at),
        )
        for m, c in rows
    ]


@router.post("/mensajes/{referencia}/estado", status_code=204)
async def marcar(referencia: str, estado: str, request: Request, settings: Settings = Depends(get_settings), claims: sess.Claims = Depends(require_staff)) -> Response:
    sess.require_same_origin(request, settings)
    sess.check_csrf(request, claims)
    if estado not in {"nuevo", "leido", "respondido"} or not referencia.startswith("NX-"):
        raise HTTPException(status_code=422, detail="Estado o referencia inválidos")
    ref = referencia[3:]
    if len(ref) != 8 or any(ch not in "0123456789abcdefABCDEF" for ch in ref):
        raise HTTPException(status_code=422, detail="Referencia inválida")
    if not await db.set_status_by_ref(staff_sessionmaker(request), ref, estado):
        raise HTTPException(status_code=404, detail="No encontrado")
    return Response(status_code=204)
