"""AES-256-GCM per-tenant encryption, report signing (RSA-PSS/SHA-256), webhook HMAC."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.keys import KeyRing


def _derive(master: bytes, tenant_id: str, purpose: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=purpose + b":" + tenant_id.encode()
    ).derive(master)


def encrypt_for_tenant(ring: KeyRing, tenant_id: str, plaintext: bytes, aad: str) -> bytes:
    """Return nonce(12) || ciphertext+tag. The tenant key never leaves memory."""
    key = _derive(ring.data_key, tenant_id, b"data")
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, f"{tenant_id}|{aad}".encode())


def decrypt_for_tenant(ring: KeyRing, tenant_id: str, blob: bytes, aad: str) -> bytes:
    key = _derive(ring.data_key, tenant_id, b"data")
    return AESGCM(key).decrypt(blob[:12], blob[12:], f"{tenant_id}|{aad}".encode())


def canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH)


def sign_bytes(ring: KeyRing, data: bytes) -> str:
    key = serialization.load_pem_private_key(ring.report_private_pem.encode(), password=None)
    return base64.b64encode(key.sign(data, _PSS, hashes.SHA256())).decode()


def verify_signature(public_pem: str, data: bytes, signature_b64: str) -> bool:
    pub = serialization.load_pem_public_key(public_pem.encode())
    try:
        pub.verify(base64.b64decode(signature_b64), data, _PSS, hashes.SHA256())
        return True
    except (InvalidSignature, ValueError):
        return False


def webhook_key(ring: KeyRing, tenant_id: str) -> bytes:
    return _derive(ring.webhook_secret, tenant_id, b"webhook")


def sign_webhook(key: bytes, timestamp: str, body: bytes) -> str:
    mac = hmac.new(key, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def verify_webhook(key: bytes, timestamp: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_webhook(key, timestamp, body), signature)
