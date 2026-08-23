"""Envelope encryption AES-256-GCM (sec-02). Puro, sin red ni base."""

from __future__ import annotations

import os

import pytest

from app.domain.crypto import MasterKey, decrypt_value, encrypt_value, new_data_key


def _master_key() -> MasterKey:
    return MasterKey(os.urandom(32))


def test_master_key_exige_32_bytes() -> None:
    with pytest.raises(ValueError):
        MasterKey(b"demasiado-corta")


def test_wrap_unwrap_dek_redondea() -> None:
    master = _master_key()
    dek = new_data_key()
    wrapped, nonce = master.wrap(dek)
    assert master.unwrap(wrapped, nonce) == dek


def test_dek_distinta_no_desenvuelve() -> None:
    master_a = _master_key()
    master_b = _master_key()
    dek = new_data_key()
    wrapped, nonce = master_a.wrap(dek)
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag de cryptography
        master_b.unwrap(wrapped, nonce)


def test_encrypt_decrypt_value_redondea() -> None:
    dek = new_data_key()
    ciphertext, nonce = encrypt_value(dek, "ghp_super_secreto")
    assert decrypt_value(dek, ciphertext, nonce) == "ghp_super_secreto"
    assert ciphertext != "ghp_super_secreto"  # nunca en claro


def test_dek_distinta_no_descifra() -> None:
    dek_a = new_data_key()
    dek_b = new_data_key()
    ciphertext, nonce = encrypt_value(dek_a, "secreto")
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag de cryptography
        decrypt_value(dek_b, ciphertext, nonce)
