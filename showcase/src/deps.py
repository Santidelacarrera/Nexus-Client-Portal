"""Dependencias compartidas: configuración, limitador, bases de datos y autenticación."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.templating import Jinja2Templates

from src.config import Settings, get_settings
from src.security import session as sess

SettingsDep = Annotated[Settings, Depends(get_settings)]


def app_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.app_sm


def staff_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    sm = request.app.state.staff_sm
    if sm is None:
        raise HTTPException(status_code=503, detail="Panel interno no configurado")
    return sm


def templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def visitor_claims(request: Request, settings: SettingsDep) -> sess.Claims | None:
    return sess.read(settings, request.cookies.get(settings.visitor_cookie_name), sess.AUD_VISITOR)


def require_visitor(request: Request, settings: SettingsDep) -> sess.Claims:
    claims = visitor_claims(request, settings)
    if claims is None:
        raise HTTPException(status_code=401, detail="Sesión no iniciada")
    return claims


def require_staff(request: Request, settings: SettingsDep) -> sess.Claims:
    claims = sess.read(settings, request.cookies.get(settings.staff_cookie_name), sess.AUD_STAFF)
    if claims is None or claims.role != "staff":
        raise HTTPException(status_code=401, detail="No autenticado")
    return claims


def visitor_uuid(claims: sess.Claims) -> uuid.UUID:
    try:
        return uuid.UUID(claims.sub)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Sesión inválida") from exc
