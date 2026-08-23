"""Firma y verificación RSA (docs/freya-api-contract.md §15). Sin red: clave
efímera en memoria."""

from __future__ import annotations

from pathlib import Path

import jwt as pyjwt
import pytest
from freya_common import INTERNAL_AUDIENCE
from jwt import PyJWK
from jwt.exceptions import PyJWTError

from app.domain.keys import KeyRing
from app.domain.tokens import SERVICE_SUBJECT, issue_service_token, issue_user_token


def _keyring() -> KeyRing:
    return KeyRing.load(Path("/no/existe"))  # fuerza la clave efímera en memoria


def _decode(token: str, jwks: dict, **kwargs) -> dict:
    kid = pyjwt.get_unverified_header(token)["kid"]
    jwk_data = next(k for k in jwks["keys"] if k["kid"] == kid)
    signing_key = PyJWK(jwk_data).key
    return pyjwt.decode(token, key=signing_key, algorithms=["RS256"], **kwargs)


def test_jwks_expone_la_clave_activa_con_kid() -> None:
    keyring = _keyring()
    jwks = keyring.jwks()
    assert jwks["keys"][0]["kid"] == keyring.active.kid
    assert jwks["keys"][0]["kty"] == "RSA"
    assert jwks["keys"][0]["alg"] == "RS256"


def test_service_token_lleva_sub_constante_e_identidad_en_service() -> None:
    keyring = _keyring()
    token, ttl = issue_service_token(
        keyring,
        service="gestor-db",
        permissions=["read:database", "write:database"],
        issuer="https://freya-auth:8002",
        ttl_seconds=300,
    )
    assert ttl == 300

    claims = _decode(
        token, keyring.jwks(), audience=INTERNAL_AUDIENCE, issuer="https://freya-auth:8002"
    )
    assert claims["sub"] == SERVICE_SUBJECT
    assert claims["service"] == "gestor-db"
    assert claims["permissions"] == ["read:database", "write:database"]


def test_user_token_lleva_sub_role_y_permissions() -> None:
    keyring = _keyring()
    token, _ = issue_user_token(
        keyring,
        user_id="usr_ABC123",
        tenant_id="freya",
        role="admin",
        permissions=["read:self", "admin:users"],
        issuer="https://freya-auth:8002",
        ttl_seconds=900,
    )
    claims = _decode(
        token, keyring.jwks(), audience=INTERNAL_AUDIENCE, issuer="https://freya-auth:8002"
    )
    assert claims["sub"] == "usr_ABC123"
    assert claims["tenant_id"] == "freya"
    assert claims["role"] == "admin"


def test_token_de_una_clave_no_verifica_con_otra() -> None:
    signer = _keyring()
    other = _keyring()
    token, _ = issue_service_token(
        signer, service="x", permissions=[], issuer="https://freya-auth:8002", ttl_seconds=60
    )
    with pytest.raises(StopIteration):
        _decode(
            token, other.jwks(), audience=INTERNAL_AUDIENCE, issuer="https://freya-auth:8002"
        )


def test_token_caducado_falla_la_verificacion() -> None:
    keyring = _keyring()
    token, _ = issue_service_token(
        keyring, service="x", permissions=[], issuer="https://freya-auth:8002", ttl_seconds=-1
    )
    with pytest.raises(PyJWTError):
        _decode(
            token, keyring.jwks(), audience=INTERNAL_AUDIENCE, issuer="https://freya-auth:8002"
        )
