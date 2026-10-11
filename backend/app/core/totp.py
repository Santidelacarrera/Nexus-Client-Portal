"""RFC 6238 TOTP (SHA-1, 6 digits, 30 s) — stdlib only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def hotp(secret_b32: str, counter: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[off : off + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def verify(secret_b32: str, code: str, *, last_counter: int = 0, now: float | None = None, window: int = 1) -> int | None:
    """Return the matched time-step counter, or None. Steps <= last_counter are rejected (replay)."""
    code = code.strip().replace(" ", "")
    if not re.fullmatch(r"\d{6}", code):
        return None
    t = int((now if now is not None else time.time()) // STEP)
    matched: int | None = None
    for c in range(t - window, t + window + 1):  # no early exit: constant work per attempt
        if hmac.compare_digest(hotp(secret_b32, c), code) and c > last_counter:
            matched = c
    return matched


def provisioning_uri(secret_b32: str, account: str, issuer: str = "Nexus Client Portal") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def new_recovery_codes(n: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def hash_recovery(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
