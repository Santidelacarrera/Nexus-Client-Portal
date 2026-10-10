"""Key material loading. Production refuses to start with ephemeral keys."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings, get_settings

log = logging.getLogger("nexus.keys")


def generate_rsa_pem(bits: int = 3072) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv, pub


def public_fingerprint(public_pem: str) -> str:
    der = serialization.load_pem_public_key(public_pem.encode()).public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()[:32]


@dataclass(frozen=True)
class KeyRing:
    jwt_private_pem: str
    jwt_public_pem: str
    report_private_pem: str
    report_public_pem: str
    data_key: bytes
    webhook_secret: bytes

    @property
    def report_key_id(self) -> str:
        return public_fingerprint(self.report_public_pem)


def _public_from_private(priv_pem: str) -> str:
    key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def load_keyring(settings: Settings | None = None) -> KeyRing:
    s = settings or get_settings()
    missing: list[str] = []

    jwt_priv = s.read_secret(s.jwt_private_key, s.jwt_private_key_path)
    jwt_pub = s.read_secret(s.jwt_public_key, s.jwt_public_key_path)
    rep_priv = s.read_secret(s.report_signing_key, s.report_signing_key_path)
    data_b64 = s.read_secret(s.data_encryption_key, s.data_encryption_key_path)
    hook = s.read_secret(s.webhook_secret, s.webhook_secret_path)

    if not jwt_priv:
        missing.append("JWT_PRIVATE_KEY")
    if not rep_priv:
        missing.append("REPORT_SIGNING_KEY")
    if not data_b64:
        missing.append("DATA_ENCRYPTION_KEY")
    if not hook:
        missing.append("WEBHOOK_SECRET")

    if missing and s.is_production:
        raise RuntimeError(f"Missing required secrets in production: {', '.join(missing)}")
    if missing:
        log.warning("Generating EPHEMERAL dev keys for: %s (never do this in production)", missing)
        if not jwt_priv:
            jwt_priv, jwt_pub = generate_rsa_pem(2048)
        if not rep_priv:
            rep_priv, _ = generate_rsa_pem(2048)
        data_b64 = data_b64 or base64.b64encode(os.urandom(32)).decode()
        hook = hook or base64.b64encode(os.urandom(32)).decode()

    data_key = base64.b64decode(data_b64)
    if len(data_key) != 32:
        raise RuntimeError("DATA_ENCRYPTION_KEY must be 32 bytes (base64)")
    return KeyRing(
        jwt_private_pem=jwt_priv,
        jwt_public_pem=jwt_pub or _public_from_private(jwt_priv),
        report_private_pem=rep_priv,
        report_public_pem=_public_from_private(rep_priv),
        data_key=data_key,
        webhook_secret=hook.encode(),
    )


_ring: KeyRing | None = None


def get_keyring() -> KeyRing:
    global _ring
    if _ring is None:
        _ring = load_keyring()
    return _ring


def reset_keyring() -> None:
    global _ring
    _ring = None
