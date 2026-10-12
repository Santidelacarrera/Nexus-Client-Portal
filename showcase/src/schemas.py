"""DTOs Pydantic v2. Las ENTRADAS son estrictas (extra=forbid); las SALIDAS son listas blancas explícitas:
nunca se serializa un modelo de base de datos, de modo que ids internos, hashes y PII no necesaria no pueden filtrarse."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.security.sanitize import clean_text

_NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '.\-]){1,119}$", re.UNICODE)


class ContactIn(BaseModel):
    """Datos mínimos imprescindibles: nombre, correo y mensaje, más la prueba de consentimiento."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    message: str = Field(min_length=10, max_length=2000)
    # Debe llegar explícitamente en true: no existe un valor por defecto "aceptado".
    consentimiento_ley_21719: Literal[True]
    # Señuelo anti-bots: las personas no lo ven ni lo rellenan.
    website: str = Field(default="", max_length=200)

    @field_validator("consentimiento_ley_21719", mode="before")
    @classmethod
    def _explicit_consent(cls, v: object) -> object:
        if v is not True:  # sin coerción: ni 1, ni "true", ni "on"
            raise ValueError("El consentimiento debe aceptarse de forma explícita (true)")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = clean_text(v)
        if not _NAME.match(v):
            raise ValueError("El nombre solo puede contener letras, espacios, apóstrofes, puntos y guiones")
        return v

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = clean_text(v)
        if len(v) < 10:
            raise ValueError("El mensaje debe tener al menos 10 caracteres de texto")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.lower()


class ContactOut(BaseModel):
    estado: Literal["recibido"] = "recibido"
    referencia: str
    recibido_en: datetime


class SessionOut(BaseModel):
    csrf_token: str
    policy_version: str


class StaffLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class StaffSessionOut(BaseModel):
    csrf_token: str


class ConsentOut(BaseModel):
    version: str
    registrado_en: datetime


class StaffMessageOut(BaseModel):
    """Vista del panel interno: lo necesario para responder; sin ids de sesión/consentimiento ni metadatos técnicos."""

    referencia: str
    nombre: str
    email: str
    mensaje: str
    estado: Literal["nuevo", "leido", "respondido"]
    recibido_en: datetime
    conservar_hasta: datetime
    consentimiento: ConsentOut


class ProjectOut(BaseModel):
    slug: str
    nombre: str
    resumen: str
    categorias: list[str]
    estado: str
    capacidades: list[str]
