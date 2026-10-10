"""Application settings. Secrets may be given inline or via *_PATH files (Docker/K8s secrets)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # development | test | production
    database_url: str = "sqlite:///./nexus_dev.db"
    # Privileged URL used ONLY by the bootstrap/seed tooling (schema + RLS DDL).
    database_admin_url: str | None = None
    db_app_role: str = "nexus_app"
    redis_url: str | None = None

    # JWT (RS256)
    jwt_private_key: str | None = None
    jwt_private_key_path: str | None = None
    jwt_public_key: str | None = None
    jwt_public_key_path: str | None = None
    jwt_issuer: str = "nexus-client-portal"
    jwt_ttl_minutes: int = 15

    # Agency report-signing key (RSA) — signs executive reports.
    report_signing_key: str | None = None
    report_signing_key_path: str | None = None
    report_signer_name: str = "Santiago de la Carrera — Nexus Security & AI Lab"

    # 32-byte master key (base64) for AES-256-GCM; per-tenant keys derived via HKDF.
    data_encryption_key: str | None = None
    data_encryption_key_path: str | None = None
    # Secret used to derive per-tenant HMAC keys for agent webhooks.
    webhook_secret: str | None = None
    webhook_secret_path: str | None = None
    webhook_max_skew_seconds: int = 300

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_ip_per_minute: int = 240
    rate_limit_tenant_per_minute: int = 600
    rate_limit_login_per_minute: int = 10
    trusted_proxies: bool = False  # honour X-Forwarded-For (behind Envoy)

    telemetry_simulator: bool = False
    simulator_interval_seconds: float = 2.5
    seed_demo_password: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def read_secret(self, inline: str | None, path: str | None) -> str | None:
        if inline:
            return inline.replace("\\n", "\n")
        if path and Path(path).is_file():
            return Path(path).read_text().strip()
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
