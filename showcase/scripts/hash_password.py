"""Genera un hash Argon2id para STAFF_PASSWORD_HASH. La contraseña se pide por teclado (no queda en el historial)."""
import getpass
import sys

from argon2 import PasswordHasher

if __name__ == "__main__":
    pw = getpass.getpass("Contraseña del panel interno (mín. 14 caracteres): ")
    if len(pw) < 14 or pw != getpass.getpass("Repite la contraseña: "):
        sys.exit("Contraseña demasiado corta o no coincide.")
    print(PasswordHasher().hash(pw))
