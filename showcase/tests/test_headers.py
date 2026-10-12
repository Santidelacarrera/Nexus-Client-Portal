import pytest




async def test_security_headers_on_pages(client):
    r = await client.get("/")
    assert r.status_code == 200
    h = r.headers
    csp = h["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "frame-ancestors 'none'" in csp
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"]
    assert h["cross-origin-resource-policy"] == "same-origin"
    assert "server" not in h or "uvicorn" not in h["server"].lower()


async def test_hsts_only_in_production(client):
    assert "strict-transport-security" not in (await client.get("/")).headers  # desarrollo sobre HTTP


async def test_headers_also_on_errors_and_api(client):
    for path in ("/no-existe", "/api/v1/proyectos"):
        r = await client.get(path)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "content-security-policy" in r.headers


async def test_untrusted_host_rejected(app):
    import httpx

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://evil.example") as c:
        assert (await c.get("/")).status_code == 400


async def test_openapi_hidden_in_production(monkeypatch):
    from src.config import Settings
    from src.main import create_app

    s = Settings(environment="production", cookie_secure=True)
    assert create_app(s).openapi_url is None
