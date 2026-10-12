"""Configuración exclusivamente por entorno (pydantic-settings). No hay secretos por defecto: si faltan, la app no arranca."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER = "pendiente de completar"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Dos conexiones con roles distintos (mínimo privilegio). Ninguno es superusuario ni BYPASSRLS.
    database_url: SecretStr
    staff_database_url: SecretStr | None = None

    session_secret: SecretStr
    cookie_secure: bool = True
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    trusted_proxy: bool = False
    ratelimit_storage_uri: str = "memory://"
    visitor_session_hours: int = 24
    staff_session_minutes: int = 30

    staff_username: str | None = None
    staff_password_hash: SecretStr | None = None

    policy_version: str = "2026-10-borrador-1"
    company_legal_name: str = ""
    privacy_contact_email: str = ""

    # Aviso por correo de cada consulta (opcional). Sin SMTP_HOST o sin CONTACT_NOTIFY_TO queda desactivado.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_timeout_seconds: int = 10
    mail_from: str = ""
    contact_notify_to: str = ""

    @field_validator("session_secret")
    @classmethod
    def _strong_secret(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET debe tener al menos 32 caracteres")
        return v

    @model_validator(mode="after")
    def _production_rules(self) -> Settings:
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE no puede ser false en producción")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    # `__Host-` obliga a Secure + Path=/ + sin Domain: la cookie no puede ser fijada por un subdominio.
    @property
    def visitor_cookie_name(self) -> str:
        return "__Host-nx_sid" if self.cookie_secure else "nx_sid"

    @property
    def staff_cookie_name(self) -> str:
        return "__Host-nx_staff" if self.cookie_secure else "nx_staff"

    def legal(self, value: str) -> str:
        """Dato legal de la empresa o un marcador visible: nunca se inventan datos."""
        return value.strip() or PLACEHOLDER


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
