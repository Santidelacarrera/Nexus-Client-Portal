import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.update(
    ENVIRONMENT="test", RATE_LIMIT_LOGIN_PER_MINUTE="100000",
    RATE_LIMIT_IP_PER_MINUTE="1000000", RATE_LIMIT_TENANT_PER_MINUTE="1000000",
    SEED_DEMO_PASSWORD="Test-Password-123!", CORS_ORIGINS='["http://localhost:3000"]',
)

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.store import reset_store
from app.db.bootstrap import apply_schema
from app.db.seed import seed
from app.db.session import get_engine
from app.main import create_app

PASSWORD = "Test-Password-123!"


@pytest.fixture(scope="session")
def client():
    admin = os.getenv("DATABASE_ADMIN_URL")
    if admin:  # PostgreSQL run: schema/RLS via owner, queries via the unprivileged app role
        from sqlalchemy import create_engine

        apply_schema(create_engine(admin))
    else:
        apply_schema(get_engine())
    seed(days=3)
    reset_store()
    with TestClient(create_app()) as c:
        yield c


def _login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def acme(client):
    d = _login(client, "ciso@acme-fintech.example")
    return {"h": {"Authorization": f"Bearer {d['access_token']}"}, **d}


@pytest.fixture(scope="session")
def acme_viewer(client):
    d = _login(client, "viewer@acme-fintech.example")
    return {"h": {"Authorization": f"Bearer {d['access_token']}"}, **d}


@pytest.fixture(scope="session")
def helix(client):
    d = _login(client, "ciso@helix-health.example")
    return {"h": {"Authorization": f"Bearer {d['access_token']}"}, **d}


@pytest.fixture()
def settings():
    return get_settings()
