"""Sanitización de texto libre con nh3 (Ammonia): se eliminan TODAS las etiquetas y su contenido peligroso.

La salida se guarda como TEXTO PLANO y se escapa al mostrarla (Jinja2 autoescape / textContent): defensa en profundidad.
"""
from __future__ import annotations

import html
import re
import unicodedata

import nh3

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL.sub("", value)
    # nh3.clean serializa como HTML (&amp;, &lt;); desescapamos una vez para recuperar el texto plano del usuario.
    return html.unescape(nh3.clean(value, tags=set())).strip()
