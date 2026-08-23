"""Hashing Argon2id y la comparación de tiempo constante (auth-02, auth-05)."""

from __future__ import annotations

from app.domain.passwords import hash_secret, verify_secret


def test_hash_y_verify_redondean() -> None:
    hashed = hash_secret("correcthorsebattery")
    assert verify_secret("correcthorsebattery", hashed) is True
    assert verify_secret("otra-cosa", hashed) is False


def test_verify_con_hash_ausente_siempre_falla() -> None:
    # None simula "no existe la fila": debe fallar igual, sin lanzar,
    # gastando el mismo trabajo que una verificación real.
    assert verify_secret("cualquiera", None) is False
