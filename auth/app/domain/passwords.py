"""Hashing Argon2id: contraseñas de usuario y client_secret de servicios
(docs/CONVENTIONS.md §4). Un único algoritmo para ambos casos."""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_secret(raw: str) -> str:
    return _hasher.hash(raw)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Hash de relleno para cuando no hay fila que comparar (auth-02/auth-05).

    Sin esto, "email desconocido" respondería más rápido que "email
    correcto, contraseña incorrecta" — una fuga de temporización que permite
    enumerar qué emails o client_id existen sin adivinar ninguna contraseña.
    """
    return _hasher.hash("freya-dummy-password-for-constant-time-checks")


def verify_secret(raw: str, hashed: str | None) -> bool:
    """hashed=None (la fila no existía) igual gasta el coste de un Argon2id."""
    target = hashed if hashed is not None else _dummy_hash()
    try:
        ok = _hasher.verify(target, raw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False
    return ok and hashed is not None
