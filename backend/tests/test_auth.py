import time

import jwt

from app.core.keys import get_keyring


def test_requests_without_header_rejected(client):
    for path in ("/api/v1/overview", "/api/v1/security/findings", "/api/v1/finops/summary", "/api/v1/rag/queries", "/api/v1/reports"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.headers["www-authenticate"] == "Bearer"


def test_garbage_and_wrong_scheme_rejected(client):
    assert client.get("/api/v1/overview", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/v1/overview", headers={"Authorization": "Basic abc"}).status_code == 401


def test_alg_none_and_hs256_confusion_rejected(client, acme):
    claims = {"iss": "nexus-client-portal", "aud": "nexus-api", "sub": acme["user"]["id"], "tid": acme["tenant"]["id"], "jti": "x", "iat": int(time.time()), "exp": int(time.time()) + 600}
    none_tok = jwt.encode(claims, None, algorithm="none")
    assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {none_tok}"}).status_code == 401
    # signed by a different RSA key
    from app.core.keys import generate_rsa_pem

    other_priv, _ = generate_rsa_pem(2048)
    forged = jwt.encode(claims, other_priv, algorithm="RS256")
    assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_expired_and_wrong_audience_rejected(client, acme):
    base = {"iss": "nexus-client-portal", "sub": acme["user"]["id"], "tid": acme["tenant"]["id"], "jti": "y", "iat": int(time.time()) - 100}
    key = get_keyring().jwt_private_pem
    expired = jwt.encode({**base, "aud": "nexus-api", "exp": int(time.time()) - 10}, key, algorithm="RS256")
    wrong_aud = jwt.encode({**base, "aud": "nexus-ws", "exp": int(time.time()) + 100}, key, algorithm="RS256")
    for tok in (expired, wrong_aud):
        assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_login_ok_and_failures(client):
    ok = client.post("/api/v1/auth/login", json={"email": "ciso@acme-fintech.example", "password": "Test-Password-123!"})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    assert "password" not in ok.text
    assert client.post("/api/v1/auth/login", json={"email": "ciso@acme-fintech.example", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ghost@nowhere.example", "password": "x"}).status_code == 401


def test_token_is_rs256_short_lived(acme):
    hdr = jwt.get_unverified_header(acme["access_token"])
    assert hdr["alg"] == "RS256"
    assert acme["expires_in"] <= 900


def test_rate_limit_on_login(client, settings):
    old = settings.rate_limit_login_per_minute
    settings.rate_limit_login_per_minute = 3
    try:
        codes = [client.post("/api/v1/auth/login", json={"email": "x@y.example", "password": "z"}).status_code for _ in range(8)]
    finally:
        settings.rate_limit_login_per_minute = old
    assert 429 in codes


def test_security_headers(client):
    r = client.get("/health")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "unsafe-inline" not in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
