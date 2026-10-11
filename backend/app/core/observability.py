"""Request IDs, structured JSON access logs and Prometheus metrics."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid

from fastapi import Request
from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_VALID_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

HTTP_REQUESTS = Counter("nexus_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("nexus_http_request_seconds", "HTTP latency", ["method", "route"], buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
AUDIT_EVENTS = Counter("nexus_audit_events_total", "Audit trail entries by action", ["action"])
WS_CONNECTIONS = Gauge("nexus_ws_connections", "Open telemetry WebSocket connections")

access_log = logging.getLogger("nexus.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name,
               "msg": record.getMessage(), "request_id": request_id_ctx.get()}
        doc.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)


def configure_logging(json_logs: bool) -> None:
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    root.setLevel(logging.INFO)
    if json_logs:
        for h in root.handlers:
            h.setFormatter(JsonFormatter())


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        inbound = request.headers.get("x-request-id", "")
        rid = inbound if _VALID_ID.match(inbound) else uuid.uuid4().hex  # never trust arbitrary log-injectable ids
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            elapsed = time.perf_counter() - start
            route_obj = request.scope.get("route")
            route = getattr(route_obj, "path", None) or ("unmatched" if status == 404 else request.url.path)
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            p = getattr(request.state, "principal", None)
            if route != "/health":
                access_log.info("request", extra={"extra_fields": {
                    "method": request.method, "route": route, "status": status, "ms": round(elapsed * 1000, 1),
                    "tenant_id": getattr(p, "tenant_id", None), "user_id": getattr(p, "user_id", None)}})
            request_id_ctx.reset(token)
