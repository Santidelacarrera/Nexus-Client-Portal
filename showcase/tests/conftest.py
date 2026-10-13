"""Fixtures: PostgreSQL 16 REAL (las garantías de RLS no se pueden simular con SQLite ni con mocks).

Requiere `TEST_ADMIN_DSN` (rol con CREATEDB/CREATEROLE, p. ej. postgresql://admin:pw@localhost/postgres).
Crea una base `showcase_test` desechable, aplica `schema.sql` y da LOGIN a los dos roles de la aplicación.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import httpx
import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parent.parent
ADMIN_DSN = os.environ.get("TEST_ADMIN_DSN")
APP_PW, STAFF_PW = "app_" + secrets.token_hex(6), "staff_" + secrets.token_hex(6)
STAFF_USER, STAFF_PASSWORD = "staff", "Staff-Password-2026!"
TEST_DB = "showcase_test"


def _dsn(db: str, user: str | None = None, pw: str | None = None, driver: str = "") -> str:
    p = urlsplit(ADMIN_DSN or "postgresql://x@localhost/postgres")
    host = p.hostname or "localhost"
    port = f":{p.port}" if p.port else ""
    cred = f"{user}:{pw}@" if user else (f"{p.username}:{p.password}@" if p.username else "")
    return urlunsplit((f"postgresql{driver}", f"{cred}{host}{port}", f"/{db}", "", ""))


if not ADMIN_DSN:
    collect_ignore_glob = ["test_*.py"]  # sin PostgreSQL no hay pruebas honestas que ejecutar
    pytest.skip("TEST_ADMIN_DSN no definido: se requiere PostgreSQL 16", allow_module_level=True)

# El entorno se fija ANTES de importar la aplicación (el limitador y la configuración se leen al importar).
from argon2 import PasswordHasher  # noqa: E402

os.environ.update(
    ENVIRONMENT="development", COOKIE_SECURE="false", SESSION_SECRET=secrets.token_urlsafe(48),
    DATABASE_URL=_dsn(TEST_DB, "showcase_app", APP_PW, "+asyncpg"), STAFF_DATABASE_URL=_dsn(TEST_DB, "showcase_staff", STAFF_PW, "+asyncpg"),
    STAFF_USERNAME=STAFF_USER, STAFF_PASSWORD_HASH=PasswordHasher().hash(STAFF_PASSWORD),
    ALLOWED_HOSTS='["testserver","localhost"]',
    COMPANY_TAX_ID="99.999.999-9", COMPANY_ADDRESS="Calle Secreta 123, Santiago",
)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def database():
    admin = await asyncpg.connect(_dsn("postgres"))
    await admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    await admin.execute(f'CREATE DATABASE "{TEST_DB}"')
    await admin.close()
    conn = await asyncpg.connect(_dsn(TEST_DB))
    await conn.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
    await conn.execute(f"ALTER ROLE showcase_app LOGIN PASSWORD '{APP_PW}' NOSUPERUSER NOBYPASSRLS")
    await conn.execute(f"ALTER ROLE showcase_staff LOGIN PASSWORD '{STAFF_PW}' NOSUPERUSER NOBYPASSRLS")
    await conn.close()
    yield
    admin = await asyncpg.connect(_dsn("postgres"))
    await admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    await admin.close()


@pytest_asyncio.fixture
async def admin_conn(database):
    """Superusuario SOLO para preparar/inspeccionar datos; las aserciones de seguridad usan los roles reales."""
    conn = await asyncpg.connect(_dsn(TEST_DB))
    yield conn
    await conn.close()


@pytest.fixture
def app_dsn() -> str:
    return _dsn(TEST_DB, "showcase_app", APP_PW)


@pytest.fixture
def staff_dsn() -> str:
    return _dsn(TEST_DB, "showcase_staff", STAFF_PW)


@pytest_asyncio.fixture
async def app(database):
    from src.config import Settings
    from src.main import create_app
    from src.routes.api import limiter

    limiter.reset()
    application = create_app(Settings())
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost", headers={"Origin": "http://localhost"}) as c:
        yield c


@pytest_asyncio.fixture
async def visitor(client):
    """Cliente con sesión anónima iniciada; devuelve (cliente, cabeceras con CSRF)."""
    r = await client.get("/api/v1/session")
    assert r.status_code == 200
    return client, {"X-CSRF-Token": r.json()["csrf_token"]}


VALID = {"name": "Ana Pérez", "email": "ana@example.com", "message": "Quiero conocer cómo funciona el portal.", "consentimiento_ley_21719": True}
