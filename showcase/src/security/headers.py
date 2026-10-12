"""Cabeceras de seguridad estrictas, inyectadas en TODA respuesta con la librería `secure`.

La CSP no admite `unsafe-inline` ni `unsafe-eval`: todo el JS y CSS son archivos propios del mismo origen, y no hay
atributos `style=""` ni manejadores `onclick=""` en las plantillas. Tampoco se permite ningún origen externo: las
tipografías y bibliotecas están auto-alojadas (sin fuga de IP a terceros antes del consentimiento).
"""
from __future__ import annotations

from secure import (
    ContentSecurityPolicy,
    CrossOriginOpenerPolicy,
    PermissionsPolicy,
    ReferrerPolicy,
    Secure,
    Server,
    StrictTransportSecurity,
    XContentTypeOptions,
    XFrameOptions,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request


def build_secure(production: bool) -> Secure:
    csp = (
        ContentSecurityPolicy()
        .default_src("'none'")
        .script_src("'self'")
        .style_src("'self'")
        .img_src("'self'", "data:")
        .font_src("'self'")
        .connect_src("'self'")
        .manifest_src("'self'")
        .form_action("'self'")
        .base_uri("'none'")
        .object_src("'none'")
        .frame_ancestors("'none'")
    )
    if production:
        csp = csp.upgrade_insecure_requests()
    return Secure(
        csp=csp,
        hsts=StrictTransportSecurity().max_age(63_072_000).include_subdomains().preload() if production else None,
        referrer=ReferrerPolicy().strict_origin_when_cross_origin(),
        xcto=XContentTypeOptions(),
        xfo=XFrameOptions().deny(),
        coop=CrossOriginOpenerPolicy().same_origin(),
        permissions=PermissionsPolicy().accelerometer().camera().geolocation().gyroscope().magnetometer().microphone().payment().usb(),
        server=Server().set(""),
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, production: bool = False) -> None:  # noqa: ANN001
        super().__init__(app)
        self._headers = {k: v for k, v in build_secure(production).headers.items() if v != ""}
        self._headers["Cross-Origin-Resource-Policy"] = "same-origin"  # no incluido en secure 1.0.1

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        response = await call_next(request)
        for key, value in self._headers.items():
            response.headers[key] = value
        if "server" in response.headers:
            del response.headers["server"]
        # Datos dinámicos y HTML nunca se cachean; los recursos estáticos sí (una hora).
        response.headers["Cache-Control"] = "public, max-age=3600" if request.url.path.startswith("/static/") else "no-store"
        return response
