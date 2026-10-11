"""API pública JSON (`/api/v1`). El tenant/identidad sale SOLO de la cookie firmada, jamás del cuerpo."""

import logging
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter

from src import db
from src.config import Settings, get_settings
from src.content import load_catalog
from src.deps import app_sessionmaker, require_visitor, visitor_claims, visitor_uuid
from src.schemas import ContactIn, ContactOut, ProjectOut, SessionOut
from src.security import session as sess
from src.security.ratelimit import build_limiter

log = logging.getLogger("showcase.api")
router = APIRouter(prefix="/api/v1", tags=["api"])
limiter: Limiter = build_limiter(get_settings().ratelimit_storage_uri)


def _ref(message_id: uuid.UUID) -> str:
    return "NX-" + message_id.hex[:8].upper()


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"estado": "ok"}


@router.get("/proyectos", response_model=list[ProjectOut])
@limiter.limit("60/minute")
async def proyectos(request: Request) -> list[ProjectOut]:  # noqa: ARG001
    return [ProjectOut(slug=p.slug, nombre=p.nombre, resumen=p.resumen, categorias=p.categorias, estado=p.estado, capacidades=p.capacidades)
            for p in load_catalog().proyectos]


@router.get("/session", response_model=SessionOut)
@limiter.limit("30/minute")
async def start_session(request: Request, response: Response, settings: Settings = Depends(get_settings)) -> SessionOut:
    """Sesión anónima y estrictamente necesaria: solo permite enlazar el consentimiento con el mensaje."""
    sm = app_sessionmaker(request)
    claims = visitor_claims(request, settings)
    ttl = settings.visitor_session_hours * 3600
    if claims is not None:
        try:
            if await db.session_exists(sm, visitor_uuid(claims)):
                return SessionOut(csrf_token=claims.csrf, policy_version=settings.policy_version)
        except HTTPException:
            pass
    sid = uuid.uuid4()
    await db.create_visitor_session(sm, sid, settings)
    token, csrf = sess.issue(settings, audience=sess.AUD_VISITOR, sub=str(sid), role="visitor", ttl_seconds=ttl)
    sess.set_cookie(response, settings, settings.visitor_cookie_name, token, ttl)
    return SessionOut(csrf_token=csrf, policy_version=settings.policy_version)


@router.post("/contacto", response_model=ContactOut, status_code=201)
@limiter.limit("5/hour")
async def contacto(body: ContactIn, request: Request, settings: Settings = Depends(get_settings)) -> ContactOut:
    sess.require_same_origin(request, settings)
    claims = require_visitor(request, settings)
    sess.check_csrf(request, claims)
    if body.website:  # señuelo rellenado: es un bot. Se responde igual que un éxito y no se guarda nada.
        log.info("honeypot triggered")
        return ContactOut(referencia="NX-00000000", recibido_en=datetime.now(timezone.utc))
    try:
        message_id, at = await db.record_contact(
            app_sessionmaker(request), visitor_uuid(claims), name=body.name, email=str(body.email), message=body.message, policy_version=settings.policy_version
        )
    except db.SessionInvalid as exc:
        raise HTTPException(status_code=409, detail="La sesión expiró. Recarga la página e inténtalo de nuevo.") from exc
    log.info("contact message stored ref=%s", _ref(message_id))  # sin PII en logs
    return ContactOut(referencia=_ref(message_id), recibido_en=at)
