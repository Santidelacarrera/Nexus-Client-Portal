"""Diagramas de arquitectura como SVG generado en el servidor.

Por qué SVG propio y no Mermaid: cero JavaScript de terceros (la CSP no permite `unsafe-eval`), cero llamadas externas,
render instantáneo y accesible (`<title>`/`<desc>` + alternativa en lista). Todo texto se escapa; ningún atributo `style`.
"""
from __future__ import annotations

from html import escape

from markupsafe import Markup

from src.content import Diagram, Node

# Métricas aproximadas del texto (Plus Jakarta Sans 11.5px / 13px). Se sobrestiman un poco a propósito.
_LABEL_CHAR_W, _LABEL_PAD, _LABEL_H = 6.4, 14, 18
_BOUNDARY_CHAR_W = 7.6
Rect = tuple[float, float, float, float]  # x, y, w, h


def _hit(a: Rect, b: Rect, margin: float = 3) -> bool:
    return not (a[0] + a[2] + margin <= b[0] or b[0] + b[2] + margin <= a[0] or a[1] + a[3] + margin <= b[1] or b[1] + b[3] + margin <= a[1])


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


_NODE_LABEL_W, _NODE_SUB_W, _NODE_PAD = 8.8, 6.6, 16  # px por carácter (15px bold / 12px) y relleno horizontal
_LABEL_LINE, _SUB_LINE = 18, 15


def _wrap(text: str, max_px: float, char_w: float) -> list[str]:
    """Ajuste de línea por palabras; una palabra más ancha que la caja se deja entera (la validación de pruebas la detecta)."""
    max_chars = max(1, int(max_px // char_w))
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if len(trial) <= max_chars or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def node_lines(n: Node) -> tuple[list[str], list[str], float]:
    """Líneas de título y subtítulo ya ajustadas al ancho de la caja, y alto total del bloque de texto."""
    room = n.w - 2 * _NODE_PAD
    title = _wrap(n.label, room, _NODE_LABEL_W)
    sub = _wrap(n.sub, room, _NODE_SUB_W) if n.sub else []
    return title, sub, len(title) * _LABEL_LINE + len(sub) * _SUB_LINE


def label_rect(text: str, cx: float, baseline: float) -> Rect:
    w = len(text) * _LABEL_CHAR_W + _LABEL_PAD
    return (cx - w / 2, baseline - _LABEL_H + 5, w, _LABEL_H)


def place_edge_labels(d: Diagram) -> list[tuple[str, Rect, float]]:
    """Coloca cada etiqueta de flecha donde no pise ninguna caja ni el título de una zona ni otra etiqueta.

    Devuelve (texto, rectángulo, línea_base). Prueba: sobre la flecha, sobre las cajas, bajo las cajas.
    Así una etiqueta larga en un hueco estrecho (p. ej. «consultas parametrizadas») sube en vez de quedar detrás de una caja.
    """
    nodes = {n.id: n for n in d.nodes}
    obstacles: list[Rect] = [(n.x, n.y, n.w, n.h) for n in d.nodes]
    obstacles += [(b.x + 14, b.y + 22 - 14, len(b.label) * _BOUNDARY_CHAR_W, 18) for b in d.boundaries]
    placed: list[tuple[str, Rect, float]] = []
    for e in d.edges:
        if not e.label:
            continue
        a, b = nodes[e.from_], nodes[e.to]
        p1, p2, orient = _anchor(a, b)
        cx = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        top, bottom = min(a.y, b.y), max(a.y + a.h, b.y + b.h)
        half = (len(e.label) * _LABEL_CHAR_W + _LABEL_PAD) / 2
        candidates = [(cx, mid_y - 8)]  # sobre la flecha
        if orient == "v":
            candidates.insert(0, (cx + half + 8, mid_y + 4))  # junto a una flecha vertical
        candidates += [(cx, top - 10), (cx, bottom + 18)]  # sobre las cajas / bajo las cajas
        chosen = None
        for lx, base in candidates:
            r = label_rect(e.label, lx, base)
            inside = r[0] >= 0 and r[0] + r[2] <= d.width and r[1] >= 0 and r[1] + r[3] <= d.height
            if inside and not any(_hit(r, o) for o in obstacles) and not any(_hit(r, q[1]) for q in placed):
                chosen = (e.label, r, base)
                break
        if chosen is None:  # último recurso: la primera opción, con su fondo opaco para que siga legible
            lx, base = candidates[0]
            chosen = (e.label, label_rect(e.label, lx, base), base)
        placed.append(chosen)
    return placed


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
    for n in d.nodes:
        title, sub, block = node_lines(n)
        cx, y = n.x + n.w // 2, n.y + (n.h - block) / 2
        parts = [f'<g class="dg-node dg-{n.kind}"><rect x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="10"/>']
        for line in title:
            y += _LABEL_LINE
            parts.append(f'<text class="dg-label" x="{cx}" y="{y - 4:.1f}" text-anchor="middle">{escape(line)}</text>')
        for line in sub:
            y += _SUB_LINE
            parts.append(f'<text class="dg-sub" x="{cx}" y="{y - 3:.1f}" text-anchor="middle">{escape(line)}</text>')
        out.append("".join(parts) + "</g>")
    # Etiquetas al final: siempre por encima de cajas y flechas, con fondo propio (nunca "detrás" de un contenedor).
    for text, (rx, ry, rw, rh), base in place_edge_labels(d):
        out.append(f'<g class="dg-edge-label-g"><rect class="dg-edge-label-bg" x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh}" rx="5"/>'
                   f'<text class="dg-edge-label" x="{rx + rw / 2:.1f}" y="{base:.1f}" text-anchor="middle">{escape(text)}</text></g>')
    out.append("</svg>")
    return Markup("".join(out))  # noqa: S704 — todo el texto de entrada pasa por html.escape
