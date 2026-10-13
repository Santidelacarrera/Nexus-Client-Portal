"""Los diagramas no deben cortar ni tapar texto: etiquetas dentro del lienzo y fuera de cajas; texto dentro de su caja."""
import pytest

from src.content import load_catalog
from src.diagrams import _hit, node_lines, place_edge_labels, render_svg

CAT = load_catalog()
DIAGRAMS = [("hero", CAT.hero_diagram)] + [(p.slug, p.diagram) for p in CAT.proyectos]


@pytest.mark.parametrize("name,d", DIAGRAMS, ids=[n for n, _ in DIAGRAMS])
def test_edge_labels_do_not_overlap_nodes_or_leave_canvas(name, d):
    for text, (x, y, w, h), _ in place_edge_labels(d):
        assert x >= 0 and y >= 0 and x + w <= d.width and y + h <= d.height, f"{name}: «{text}» fuera del lienzo"
        assert not any(_hit((x, y, w, h), (n.x, n.y, n.w, n.h)) for n in d.nodes), f"{name}: «{text}» tapa una caja"


@pytest.mark.parametrize("name,d", DIAGRAMS, ids=[n for n, _ in DIAGRAMS])
def test_node_text_fits_inside_box_and_boxes_inside_zones(name, d):
    for n in d.nodes:
        _, _, block = node_lines(n)
        assert block <= n.h - 8, f"{name}: texto de «{n.label}» no cabe en la caja"
        assert n.x + n.w <= d.width and n.y + n.h <= d.height
        zones = [b for b in d.boundaries if not (n.x + n.w <= b.x or b.x + b.w <= n.x or n.y + n.h <= b.y or b.y + b.h <= n.y)]
        assert all(b.x <= n.x and n.x + n.w <= b.x + b.w and b.y <= n.y and n.y + n.h <= b.y + b.h for b in zones), f"{name}: «{n.label}» cruza el borde de una zona"


def test_labels_are_drawn_after_nodes():
    svg = str(render_svg(CAT.hero_diagram, "t"))
    assert svg.rfind('class="dg-node') < svg.find('class="dg-edge-label-g"')
