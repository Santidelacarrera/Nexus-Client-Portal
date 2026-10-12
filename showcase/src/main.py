"""Nexus Showcase — aplicación FastAPI: sitio comercial + API de contacto con consentimiento auditable."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.templating import Jinja2Templates

from src import db
from src.config import Settings, get_settings
from src.content import load_catalog
from src.routes import api, pages, staff
from src.security.headers import SecurityHeadersMiddleware
from src.security.ratelimit import rate_limit_handler

BASE = Path(__file__).resolve().parent
log = logging.getLogger("showcase")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    load_catalog()  # valida el contenido al arrancar: un JSON inválido impide el despliegue

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_engine = db.make_engine(settings.database_url.get_secret_value())
        staff_engine = db.make_engine(settings.staff_database_url.get_secret_value()) if settings.staff_database_url else None
        app.state.app_sm = db.make_sessionmaker(app_engine)
        app.state.staff_sm = db.make_sessionmaker(staff_engine) if staff_engine else None
        yield
        await app_engine.dispose()
        if staff_engine:
            await staff_engine.dispose()

    app = FastAPI(
        title="Nexus Showcase", version="1.0.0", lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs", redoc_url=None, openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.limiter = api.limiter
    app.state.templates = Jinja2Templates(directory=str(BASE / "templates"))  # autoescape activado por defecto para .html
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)  # type: ignore[arg-type]

    # Orden: el último añadido es el más externo.
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=settings.is_production)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
    app.include_router(pages.router)
    app.include_router(api.router)
    app.include_router(staff.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", ""):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
        return app.state.templates.TemplateResponse(request, "error.html", {"status": exc.status_code, "settings": settings, "catalog": load_catalog()}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # noqa: ARG001
        log.exception("unhandled error")  # el detalle queda en logs; el cliente no recibe trazas
        return HTMLResponse("Error interno", status_code=500) if "text/html" in request.headers.get("accept", "") else JSONResponse({"detail": "Error interno"}, status_code=500)

    return app




def app_factory() -> FastAPI:
    """uvicorn --factory src.main:app_factory"""
    return create_app()
