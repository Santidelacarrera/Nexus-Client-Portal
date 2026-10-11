"""Contenido de la vitrina: versionado en `content/projects.json` y validado con Pydantic (falla al arrancar si es inválido)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTENT_FILE = Path(__file__).resolve().parent.parent / "content" / "projects.json"
Kind = Literal["actor", "service", "store", "agent", "ok", "stop"]
Tone = Literal["untrusted", "tenant", "gov"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Boundary(Strict):
    label: str
    x: int
    y: int
    w: int
    h: int
    tone: Tone


class Node(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    sub: str = ""
    x: int
    y: int
    w: int
    h: int
    kind: Kind


class Edge(Strict):
    from_: str = Field(alias="from")
    to: str
    label: str = ""
    style: Literal["solid", "dashed"] = "solid"


class Diagram(Strict):
    titulo: str
    width: int
    height: int
    boundaries: list[Boundary]
    nodes: list[Node]
    edges: list[Edge]

    @model_validator(mode="after")
    def _edges_reference_nodes(self) -> Diagram:
        ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.from_ not in ids or e.to not in ids:
                raise ValueError(f"arista con nodo inexistente: {e.from_} -> {e.to}")
        return self


class Project(Strict):
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    nombre: str
    resumen: str
    para_quien: str
    categorias: list[str]
    estado: str
    destacado: bool = False
    capacidades: list[str]
    diagram: Diagram


class Catalog(Strict):
    hero_diagram: Diagram
    proyectos: list[Project]

    def by_slug(self, slug: str) -> Project | None:
        return next((p for p in self.proyectos if p.slug == slug), None)

    @property
    def categorias(self) -> list[str]:
        return sorted({c for p in self.proyectos for c in p.categorias})


@lru_cache
def load_catalog() -> Catalog:
    return Catalog.model_validate(json.loads(CONTENT_FILE.read_text(encoding="utf-8")))
