"""Claves de firma RSA y publicación JWKS (docs/freya-api-contract.md §15.1).

Cada clave vive en su propio fichero PEM en signing_keys_dir. El kid es la
huella (16 hex de SHA-256 de la clave pública DER) — nunca del nombre de
fichero, que sólo ordena por antigüedad. La más nueva firma; todas se
publican en el JWKS, así que un token ya emitido con una clave anterior
sigue verificando mientras esa clave no se borre.
"""

from __future__ import annotations

import hashlib
import logging
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
    generate_private_key,
)
from freya_common import DependencyUnavailable

logger = logging.getLogger(__name__)


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    raw = value.to_bytes(length, "big")
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class SigningKey:
    kid: str
    private_key: RSAPrivateKey
    public_key: RSAPublicKey

    @property
    def private_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def jwk(self) -> dict[str, str]:
        numbers = self.public_key.public_numbers()
        return {
            "kty": "RSA",
            "kid": self.kid,
            "use": "sig",
            "alg": "RS256",
            "n": _b64url_uint(numbers.n),
            "e": _b64url_uint(numbers.e),
        }


class KeyRing:
    """Todas las claves conocidas. La primera (más nueva) firma."""

    def __init__(self, keys: list[SigningKey]) -> None:
        if not keys:
            raise DependencyUnavailable("no hay claves de firma disponibles")
        self._keys = keys

    @property
    def active(self) -> SigningKey:
        return self._keys[0]

    def find(self, kid: str) -> SigningKey | None:
        return next((key for key in self._keys if key.kid == kid), None)

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        return {"keys": [key.jwk() for key in self._keys]}

    def merge(self, extra: list[tuple[str, SigningKey]]) -> KeyRing:
        """Añade claves de otra fuente (secrets, ver
        app/infra/secrets_keys.py) y reordena por antigüedad. `extra` es
        (marca_de_tiempo_ordenable, clave) -- las claves de fichero usan el
        nombre del PEM (AAAAMMDDHHMMSS) como marca; las de secrets, su
        `created_at` ISO -- ambas ordenan igual lexicográficamente, así que
        se pueden mezclar en una sola lista sin convertir nada."""
        # Las claves de fichero no traen su marca aparte, así que se
        # reconstruye la lista completa (self) etiquetada, se añade lo
        # nuevo (ignorando kids repetidos -- ya está), y se reordena.
        by_kid = {key.kid: key for key in self._keys}
        tagged: list[tuple[str, SigningKey]] = [
            (str(i).zfill(20), key) for i, key in enumerate(reversed(self._keys))
        ]
        for stamp, key in extra:
            if key.kid in by_kid:
                continue
            tagged.append((stamp, key))
            by_kid[key.kid] = key
        tagged.sort(key=lambda t: t[0])
        return KeyRing([key for _, key in reversed(tagged)])

    @classmethod
    def load(cls, directory: Path) -> KeyRing:
        # El nombre de fichero es una marca de tiempo (ver
        # New-FreyaSigningKey): orden ascendente = más vieja primero.
        files = sorted(directory.glob("*.pem"))
        keys: list[SigningKey] = []
        for path in files:
            private_key = serialization.load_pem_private_key(
                path.read_bytes(), password=None
            )
            if not isinstance(private_key, RSAPrivateKey):
                continue
            public_key = private_key.public_key()
            der = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            kid = hashlib.sha256(der).hexdigest()[:16]
            keys.append(
                SigningKey(kid=kid, private_key=private_key, public_key=public_key)
            )
        keys.reverse()  # más nueva primero

        if not keys:
            # Sin claves montadas (tests con --network none, o un arranque
            # antes de `.\freya.ps1 signing-key auth`): se genera una
            # efímera en memoria para no tumbar el proceso. En un despliegue
            # real, signing_keys_dir siempre trae al menos una.
            logger.warning(
                "no hay claves de firma en disco, se genera una efímera en memoria"
            )
            keys = [_ephemeral_key()]

        return cls(keys)


def key_from_pem(pem: bytes) -> SigningKey:
    private_key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(private_key, RSAPrivateKey):
        raise ValueError("la clave no es RSA")
    public_key = private_key.public_key()
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    kid = hashlib.sha256(der).hexdigest()[:16]
    return SigningKey(kid=kid, private_key=private_key, public_key=public_key)


def _ephemeral_key() -> SigningKey:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    kid = hashlib.sha256(der).hexdigest()[:16]
    return SigningKey(kid=kid, private_key=private_key, public_key=public_key)
