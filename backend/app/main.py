from __future__ import annotations

import asyncio
import hmac
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ask, audit, auth, finops, mfa, overview, rag, reports, security, webhooks, ws
from app.core.config import get_settings
from app.core.keys import get_keyring
from app.core.observability import ObservabilityMiddleware, configure_logging
from app.core.security import AuthMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.core.store import get_store
from app.db.bootstrap import apply_schema
from app.db.session import get_engine
from app.services import simulator

log = logging.getLogger("nexus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.json_logs or s.is_production)
    get_keyring()  # fail fast in production when secrets are missing
    await get_store().connect()
    if not s.is_production and s.database_url.startswith("sqlite"):
        apply_schema(get_engine())  # dev convenience; production uses `python -m app.db.bootstrap`
    task = asyncio.create_task(simulator.run(s.simulator_interval_seconds)) if s.telemetry_simulator else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await get_store().close()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Nexus Client Portal API", version="1.0.0", lifespan=lifespan,
        docs_url=None if s.is_production else "/docs", redoc_url=None, openapi_url=None if s.is_production else "/openapi.json",
    )
    # Order: last added = outermost. CORS → headers → rate limit → auth → routes.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
    )

    api = APIRouter(prefix="/api/v1")
    for r in (auth.router, mfa.router, ask.router, overview.router, security.router, finops.router, rag.router, reports.router, audit.router, webhooks.router):
        api.include_router(r)
    app.include_router(api)
    app.include_router(ws.router)

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> Response:
        """Prometheus scrape endpoint. Off (404) unless METRICS_TOKEN is configured; bearer-protected."""
        token = get_settings().metrics_token
        if not token:
            raise HTTPException(status_code=404)
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
