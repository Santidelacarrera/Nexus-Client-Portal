"""Accesibilidad estructural (WCAG 2.1 AA), CSP-compatibilidad y veracidad del contenido legal/comercial."""
import re
from html.parser import HTMLParser

import pytest

PAGES = ["/", "/privacidad", "/terminos", "/cookies", "/proyectos/nexus-client-portal", "/proyectos/contextrag-engine", "/proyectos/multiagent-consensus"]


class Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1 = 0; self.lang = None; self.imgs_without_alt = []; self.inline = []; self.external = []
        self.ids = []; self.label_for = set(); self.controls = []; self.landmarks = set(); self.skip = False; self.title = False
        self.hrefs = []; self.in_label = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html": self.lang = a.get("lang")
        if tag == "h1": self.h1 += 1
        if tag == "title": self.title = True
        if tag == "img" and "alt" not in a: self.imgs_without_alt.append(a.get("src"))
        if tag in ("main", "nav", "header", "footer"): self.landmarks.add(tag)
        if tag == "style" or tag == "script" and not a.get("src"): self.inline.append(tag)
        if "style" in a: self.inline.append("style=")
        self.inline += [k for k in a if k.startswith("on")]
        for k in ("src", "href", "action"):
            if a.get(k, "").startswith(("http://", "https://", "//")) and k != "href":
                self.external.append(a[k])
        if tag == "a" and a.get("href"): self.hrefs.append(a["href"])
        if a.get("id"): self.ids.append(a["id"])
        if tag == "label":
            self.in_label += 1
            if a.get("for"): self.label_for.add(a["for"])
        if tag in ("input", "textarea", "select") and a.get("type") not in ("hidden", "submit", "button"):
            self.controls.append((a.get("id"), a.get("aria-label") or ("implícita" if self.in_label else None), a.get("aria-labelledby")))
        if tag == "a" and a.get("href", "").startswith("#contenido"): self.skip = True

    def handle_endtag(self, tag):
        if tag == "label":
            self.in_label -= 1


@pytest.mark.parametrize("path", PAGES)
async def test_page_structure(client, path):
    r = await client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    p = Audit(); p.feed(r.text)
    assert p.lang == "es"
    assert p.h1 == 1, "exactamente un h1"
    assert not p.imgs_without_alt
    assert not p.inline, f"CSP: nada en línea ({p.inline})"
    assert not p.external, f"sin recursos de terceros: {p.external}"
    assert len(p.ids) == len(set(p.ids)), "ids duplicados"
    assert {"main", "nav", "header", "footer"} <= p.landmarks
    assert p.skip, "enlace 'saltar al contenido'"
    for cid, label, labelledby in p.controls:
        assert label or labelledby or (cid and cid in p.label_for), f"control sin etiqueta: {cid}"


@pytest.mark.parametrize("path", ["/privacidad", "/terminos", "/cookies"])
async def test_legal_pages_are_visible_drafts(client, path):
    html = (await client.get(path)).text
    assert "Sujeto a revisión legal" in html
    assert 'class="todo"' in html  # datos de la empresa no inventados


async def test_privacy_mentions_law_and_rights(client):
    text = (await client.get("/privacidad")).text
    assert "21.719" in text
    for right in ("acceso", "rectificación", "supresión"):
        assert right in text.lower()


async def test_form_has_consent_and_no_extra_fields(client):
    html = (await client.get("/")).text
    assert 'name="consentimiento_ley_21719"' in html
    names = set(re.findall(r'<(?:input|textarea)[^>]*\bname="([^"]+)"', html))
    assert {"name", "email", "message", "consentimiento_ley_21719"} <= names
    assert not {"phone", "telefono", "rut", "company"} & names, "minimización de datos"


async def test_no_invented_testimonials(client):
    html = (await client.get("/")).text.lower()
    for word in ("testimonio", "★", "clientes satisfechos", "+500", "trusted by"):
        assert word not in html


async def test_cookie_banner_and_policy_meta_present(client):
    html = (await client.get("/")).text
    assert 'id="cookie-banner"' in html or "cookie-banner" in html
    assert 'name="policy-version"' in html
    assert "Rechazar opcionales" in html


def _lum(hex_):
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("fg,bg,minimum", [
    ("#e2e8f0", "#090A0F", 4.5),   # texto base
    ("#cbd5e1", "#090A0F", 4.5),   # texto secundario
    ("#94a3b8", "#090A0F", 4.5),   # texto terciario
    ("#090A0F", "#3B82F6", 4.5),   # botón primario: texto oscuro sobre azul de acento
    ("#60a5fa", "#090A0F", 4.5),   # enlaces
    ("#34d399", "#090A0F", 4.5),   # éxito/verificado
    ("#3B82F6", "#090A0F", 3.0),   # anillo de foco / bordes de componentes (WCAG 1.4.11)
])
def test_color_contrast(fg, bg, minimum):
    assert _ratio(fg, bg) >= minimum


async def test_rut_and_domicilio_never_appear(app, client):
    """Decisión del dueño: ni RUT ni domicilio en ninguna página, ni siquiera si alguien los pone en el entorno."""
    import os

    os.environ["COMPANY_TAX_ID"] = "99.999.999-9"
    os.environ["COMPANY_ADDRESS"] = "Calle Falsa 123, Santiago"
    try:
        from src.config import Settings, get_settings

        app.dependency_overrides[get_settings] = lambda: Settings(company_legal_name="Nexus Security & AI Lab", privacy_contact_email="privacidad@example.test")
        for path in PAGES + ["/staff", "/no-existe"]:
            html = (await client.get(path)).text
            assert "99.999.999-9" not in html and "Calle Falsa" not in html, path
            low = html.lower()
            assert "rut" not in re.findall(r"\b[a-záéíóúñ]+\b", low), path
            assert "domicilio" not in low, path
        assert "privacidad@example.test" in (await client.get("/privacidad")).text  # lo demás sí se muestra
    finally:
        os.environ.pop("COMPANY_TAX_ID", None); os.environ.pop("COMPANY_ADDRESS", None)
