"""Páginas HTML (render en servidor con Jinja2, autoescape activado)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from src.config import Settings, get_settings
from src.content import load_catalog
from src.deps import templates
from src.diagrams import render_svg, steps

router = APIRouter(include_in_schema=False)


def site(settings: Settings) -> dict:
    """Solo valores públicos: la plantilla nunca recibe secretos ni cadenas de conexión."""
    return {
        "policy_version": settings.policy_version,
        "legal_name": settings.company_legal_name.strip() or "Nexus Security SpA",
    }


def ctx(request: Request, settings: Settings, **extra: object) -> dict:
    return {"site": site(settings), "catalog": load_catalog(), "render_svg": render_svg, "diagram_steps": steps, **extra}


@router.api_route("/", methods=["GET", "HEAD"])
async def home(request: Request, settings: Settings = Depends(get_settings)):
    return templates(request).TemplateResponse(request, "index.html", ctx(request, settings))


@router.api_route("/proyectos/{slug}", methods=["GET", "HEAD"])
async def project_page(slug: str, request: Request, settings: Settings = Depends(get_settings)):
    """Página completa (funciona sin JavaScript). Con JS, la vitrina abre el fragmento en un diálogo."""
    project = load_catalog().by_slug(slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return templates(request).TemplateResponse(request, "project_page.html", ctx(request, settings, p=project))


@router.api_route("/proyectos/{slug}/fragmento", methods=["GET", "HEAD"])
async def project_fragment(slug: str, request: Request, settings: Settings = Depends(get_settings)):
    """Fragmento HTML para el diálogo de la vitrina (el cliente lo sanea con DOMPurify antes de insertarlo)."""
    project = load_catalog().by_slug(slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return templates(request).TemplateResponse(request, "partials/project_detail.html", ctx(request, settings, p=project))


@router.api_route("/privacidad", methods=["GET", "HEAD"])
async def privacy(request: Request, settings: Settings = Depends(get_settings)):
    return templates(request).TemplateResponse(request, "legal/privacidad.html", ctx(request, settings, page_title="Política de privacidad"))


@router.api_route("/terminos", methods=["GET", "HEAD"])
async def terms(request: Request, settings: Settings = Depends(get_settings)):
    return templates(request).TemplateResponse(request, "legal/terminos.html", ctx(request, settings, page_title="Términos y condiciones"))


@router.api_route("/cookies", methods=["GET", "HEAD"])
async def cookies(request: Request, settings: Settings = Depends(get_settings)):
    return templates(request).TemplateResponse(request, "legal/cookies.html", ctx(request, settings, page_title="Política de cookies"))


@router.api_route("/staff", methods=["GET", "HEAD"])
async def staff_panel(request: Request, settings: Settings = Depends(get_settings)):
    response = templates(request).TemplateResponse(request, "staff.html", ctx(request, settings, page_title="Panel interno"))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots() -> str:
    return "User-agent: *\nDisallow: /staff\nDisallow: /api/\n"


@router.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon() -> Response:
    return RedirectResponse("/static/img/favicon.svg", status_code=308)
