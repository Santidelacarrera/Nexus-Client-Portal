"""Diagramas de arquitectura como SVG generado en el servidor.

Por qué SVG propio y no Mermaid: cero JavaScript de terceros (la CSP no permite `unsafe-eval`), cero llamadas externas,
render instantáneo y accesible (`<title>`/`<desc>` + alternativa en lista). Todo texto se escapa; ningún atributo `style`.
"""
from __future__ import annotations

from html import escape

from markupsafe import Markup

from src.content import Diagram, Node

_ANCHOR_GAP = 0


def _anchor(a: Node, b: Node) -> tuple[tuple[int, int], tuple[int, int], str]:
    """Puntos de salida/entrada y orientación (h = flujo horizontal, v = vertical)."""
    if b.x >= a.x + a.w - 4:
        return (a.x + a.w, a.y + a.h // 2), (b.x, b.y + b.h // 2), "h"
    if a.x >= b.x + b.w - 4:
        return (a.x, a.y + a.h // 2), (b.x + b.w, b.y + b.h // 2), "h"
    if b.y >= a.y:
        return (a.x + a.w // 2, a.y + a.h), (b.x + b.w // 2, b.y), "v"
    return (a.x + a.w // 2, a.y), (b.x + b.w // 2, b.y + b.h), "v"


def _path(p1: tuple[int, int], p2: tuple[int, int], orient: str) -> str:
    (x1, y1), (x2, y2) = p1, p2
    if orient == "h":
        mid = (x1 + x2) // 2
        return f"M{x1} {y1} H{mid} V{y2} H{x2}" if y1 != y2 else f"M{x1} {y1} H{x2}"
    mid = (y1 + y2) // 2
    return f"M{x1} {y1} V{mid} H{x2} V{y2}" if x1 != x2 else f"M{x1} {y1} V{y2}"


def steps(d: Diagram) -> list[str]:
    """Alternativa textual del diagrama (también alimenta el `<desc>` del SVG)."""
    names = {n.id: n.label for n in d.nodes}
    out = []
    for e in d.edges:
        link = f"{names[e.from_]} se conecta con {names[e.to]}"
        out.append(f"{link} ({e.label})." if e.label else f"{link}.")
    return out


def render_svg(d: Diagram, uid: str, animate: bool = False) -> Markup:
    nodes = {n.id: n for n in d.nodes}
    t, desc = f"{uid}-t", f"{uid}-d"
    out = [
        f'<svg class="dg{" dg-animate" if animate else ""}" viewBox="0 0 {d.width} {d.height}" role="img" '
        f'aria-labelledby="{t} {desc}" xmlns="http://www.w3.org/2000/svg" focusable="false">',
        f'<title id="{t}">{escape(d.titulo)}</title>',
        f'<desc id="{desc}">{escape(" ".join(steps(d)))}</desc>',
        f'<defs><marker id="{uid}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path class="dg-arrowhead" d="M0 0 L10 5 L0 10 z"/></marker></defs>',
    ]
    for b in d.boundaries:
        out.append(f'<g class="dg-boundary dg-{b.tone}"><rect x="{b.x}" y="{b.y}" width="{b.w}" height="{b.h}" rx="14"/>'
                   f'<text x="{b.x + 14}" y="{b.y + 22}">{escape(b.label)}</text></g>')
    for e in d.edges:
        p1, p2, o = _anchor(nodes[e.from_], nodes[e.to])
        cls = "dg-edge dg-dashed" if e.style == "dashed" else "dg-edge"
        out.append(f'<path class="{cls}" d="{_path(p1, p2, o)}" pathLength="1" marker-end="url(#{uid}-arrow)"/>')
        if e.label:
            lx, ly = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2 - 8
            out.append(f'<text class="dg-edge-label" x="{lx}" y="{ly}" text-anchor="middle">{escape(e.label)}</text>')
    for n in d.nodes:
        out.append(f'<g class="dg-node dg-{n.kind}"><rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="10"/>'
                   f'<text class="dg-label" x="{n.x + n.w // 2}" y="{n.y + n.h // 2 - (4 if n.sub else -5)}" text-anchor="middle">{escape(n.label)}</text>'
                   + (f'<text class="dg-sub" x="{n.x + n.w // 2}" y="{n.y + n.h // 2 + 16}" text-anchor="middle">{escape(n.sub)}</text>' if n.sub else "")
                   + "</g>")
    out.append("</svg>")
    return Markup("".join(out))  # noqa: S704 — todo el texto de entrada pasa por html.escape
