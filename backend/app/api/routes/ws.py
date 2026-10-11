from __future__ import annotations

import asyncio
import contextlib

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.observability import WS_CONNECTIONS
from app.core.security import WS_AUDIENCE, client_ip, decode_token
from app.core.store import get_store
from app.db.session import tenant_session
from app.services import bus
from app.services.audit import append_audit

router = APIRouter()


def _audit_connect(tenant_id: str, user_id: str, ip: str) -> None:
    with tenant_session(tenant_id) as db:
        append_audit(db, tenant_id, "telemetry.connect", user_id=user_id, ip=ip)
        db.commit()


@router.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket) -> None:
    """Stream of events for the caller's tenant. Auth: single-use ticket from POST /auth/ws-ticket."""
    origin = ws.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        await ws.close(code=4403)
        return
    try:
        p = decode_token(ws.query_params.get("ticket", ""), audience=WS_AUDIENCE)
    except jwt.PyJWTError:
        await ws.close(code=4401)
        return
    if not await get_store().set_once(f"ws-ticket:{p.jti}", 60):  # replay protection
        await ws.close(code=4401)
        return
    await ws.accept()
    WS_CONNECTIONS.inc()
    await run_in_threadpool(_audit_connect, p.tenant_id, p.user_id, client_ip(ws))  # type: ignore[arg-type]
    await ws.send_json({"type": "hello", "tenant_id": p.tenant_id})

    async def pump() -> None:
        async for event in bus.subscribe(p.tenant_id):  # channel derived from verified claim only
            await ws.send_json(event)

    task = asyncio.create_task(pump())
    try:
        while True:
            await ws.receive_text()  # keeps the connection alive; client messages are ignored
    except WebSocketDisconnect:
        pass
    finally:
        WS_CONNECTIONS.dec()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
