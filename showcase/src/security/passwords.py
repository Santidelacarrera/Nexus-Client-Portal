"""Contraseñas con Argon2id (argon2-cffi). Verificación en tiempo casi constante aun si el usuario no existe."""
from __future__ import annotations

import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id por defecto, parámetros RFC 9106 (perfil bajo en memoria)
_DUMMY_HASH = _hasher.hash("nexus-showcase-timing-equaliser")


def verify_staff(username: str, password: str, expected_username: str | None, expected_hash: str | None) -> bool:
    user_ok = bool(expected_username) and hmac.compare_digest(username.encode(), (expected_username or "").encode())
    try:
        ok = _hasher.verify(expected_hash if (user_ok and expected_hash) else _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return bool(ok and user_ok and expected_hash)
