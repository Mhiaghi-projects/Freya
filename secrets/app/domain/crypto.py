"""Envelope encryption AES-256-GCM (docs/ROADMAP.md sec-02).

Una clave maestra (montada en fichero, nunca en la base) envuelve una clave
de datos (DEK) aleatoria por tenant; la DEK cifra los valores de los
secretos. Rotar la master key sólo re-envuelve la DEK — no hace falta
re-cifrar cada secreto individualmente.
"""

from __future__ import annotations

import logging
import os
from base64 import b64decode, b64encode
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_NONCE_SIZE = 12
_KEY_SIZE = 32


def _b64(data: bytes) -> str:
    return b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return b64decode(data)


class MasterKey:
    def __init__(self, key_bytes: bytes) -> None:
        if len(key_bytes) != _KEY_SIZE:
            raise ValueError("la master key debe ser de 32 bytes (AES-256)")
        self._aesgcm = AESGCM(key_bytes)

    @classmethod
    def from_hex_file(cls, path: Path) -> MasterKey:
        try:
            hex_text = path.read_text(encoding="utf-8").strip()
            return cls(bytes.fromhex(hex_text))
        except (OSError, ValueError):
            # Sin master key montada (tests con --network none, o un
            # arranque antes de `.\freya.ps1 secret secrets master_key`):
            # se genera una efímera en memoria para no tumbar el proceso.
            # En un despliegue real, master_key_file siempre existe.
            logger.warning(
                "no hay master key en disco, se genera una efímera en memoria"
            )
            return cls(os.urandom(_KEY_SIZE))

    def wrap(self, dek: bytes) -> tuple[str, str]:
        """Cifra una DEK. Devuelve (wrapped_b64, nonce_b64)."""
        nonce = os.urandom(_NONCE_SIZE)
        wrapped = self._aesgcm.encrypt(nonce, dek, None)
        return _b64(wrapped), _b64(nonce)

    def unwrap(self, wrapped_b64: str, nonce_b64: str) -> bytes:
        return self._aesgcm.decrypt(_unb64(nonce_b64), _unb64(wrapped_b64), None)


def new_data_key() -> bytes:
    return os.urandom(_KEY_SIZE)


def encrypt_value(dek: bytes, value: str) -> tuple[str, str]:
    """Cifra un valor con la DEK del tenant. Devuelve (ciphertext_b64, nonce_b64)."""
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(dek).encrypt(nonce, value.encode("utf-8"), None)
    return _b64(ciphertext), _b64(nonce)


def decrypt_value(dek: bytes, ciphertext_b64: str, nonce_b64: str) -> str:
    plaintext = AESGCM(dek).decrypt(_unb64(nonce_b64), _unb64(ciphertext_b64), None)
    return plaintext.decode("utf-8")
