import time


from app.core import totp
from app.core.store import get_store
from tests.conftest import PASSWORD


def test_rfc6238_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32("12345678901234567890")
    for t, expected in [(59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")]:
        assert totp.hotp(secret, t // 30) == expected
        assert totp.verify(secret, expected, now=t, window=0) == t // 30


def test_totp_window_and_replay():
    s = totp.new_secret()
    now = 1_700_000_000
    code = totp.hotp(s, now // 30)
    assert totp.verify(s, code, now=now) == now // 30
    assert totp.verify(s, code, last_counter=now // 30, now=now) is None  # replay
    assert totp.verify(s, code, now=now + 300) is None  # outside window
    assert totp.verify(s, "abcdef", now=now) is None


def _login(client, email):
    return client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


def test_mfa_full_flow(client):
    import anyio

    email = "analyst@helix-health.example"
    d = _login(client, email).json()
    h = {"Authorization": f"Bearer {d['access_token']}"}
    assert client.get("/api/v1/auth/mfa/status", headers=h).json()["enabled"] is False

    setup = client.post("/api/v1/auth/mfa/setup", headers=h).json()
    assert setup["uri"].startswith("otpauth://totp/") and setup["secret"] in setup["uri"]
    assert client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=h).status_code == 422
    code = totp.hotp(setup["secret"], int(time.time() // 30))
    recovery = client.post("/api/v1/auth/mfa/enable", json={"code": code}, headers=h).json()["recovery_codes"]
    assert len(recovery) == 8

    # password alone no longer yields a session
    r = _login(client, email).json()
    assert r["mfa_required"] and r["access_token"] is None and r["mfa_token"]
    challenge = r["mfa_token"]
    assert client.get("/api/v1/overview", headers={"Authorization": f"Bearer {challenge}"}).status_code == 401  # wrong audience

    # the code just used at enrolment is replay-protected
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge, "code": code}).status_code == 401
    # next step's code works (clock-skew window), then the challenge is single-use
    nxt = totp.hotp(setup["secret"], int(time.time() // 30) + 1)
    ok = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge, "code": nxt})
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": challenge, "code": recovery[0]}).status_code == 401

    # recovery code logs in exactly once
    ch2 = _login(client, email).json()["mfa_token"]
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": ch2, "code": recovery[0]}).status_code == 200
    ch3 = _login(client, email).json()["mfa_token"]
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": ch3, "code": recovery[0]}).status_code == 401

    # wrong codes feed the account lockout
    for _ in range(5):
        client.post("/api/v1/auth/mfa/verify", json={"mfa_token": ch3, "code": "111111"})
    assert client.post("/api/v1/auth/mfa/verify", json={"mfa_token": ch3, "code": recovery[1]}).status_code == 429
    anyio.run(get_store().delete, f"lock:{email}")

    # disabling requires a valid code
    full = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.post("/api/v1/auth/mfa/disable", json={"code": "222222"}, headers=full).status_code == 422
    assert client.post("/api/v1/auth/mfa/disable", json={"code": recovery[1]}, headers=full).status_code == 204
    assert _login(client, email).json()["access_token"]  # back to password-only


def test_secret_is_encrypted_at_rest(client):
    from sqlalchemy import select

    from app.db.models import User
    from app.db.session import system_session

    d = _login(client, "ciso@helix-health.example").json()
    h = {"Authorization": f"Bearer {d['access_token']}"}
    secret = client.post("/api/v1/auth/mfa/setup", headers=h).json()["secret"]
    with system_session() as db:
        blob = db.scalars(select(User.mfa_secret_enc).where(User.email == "ciso@helix-health.example")).first()
    assert secret.encode() not in blob
    with system_session() as db:  # leave the account clean for other tests
        u = db.scalars(select(User).where(User.email == "ciso@helix-health.example")).first()
        u.mfa_secret_enc = None
        db.commit()
