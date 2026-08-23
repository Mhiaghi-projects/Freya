"""admin_principal/user_principal deben rechazar un JWT válido pero emitido
para OTRO tenant -- ver docs/DECISIONS.md, fallo real encontrado en la
auditoría de 2026-08-23: el token sólo se comprobaba por role/tipo, nunca
contra el tenant de la petición (X-Tenant-Context), así que un JWT admin de
un tenant funcionaba igual de bien contra cualquier otro."""

from __future__ import annotations

from pathlib import Path

import pytest
from freya_common import Forbidden
from freya_common.context import set_tenant

import app.deps as deps_module
from app.config import Settings
from app.deps import admin_principal, user_principal
from app.domain.keys import KeyRing
from app.domain.tokens import issue_user_token


class _FakeJwks:
    def __init__(self, jwks: dict) -> None:
        self._jwks = jwks

    async def keys(self, force: bool = False) -> dict:
        return self._jwks


class _FakeVerifier:
    """Envuelve freya_common.TokenVerifier con el JWKS de un keyring ya en
    memoria -- sin red, mismo patrón que tests/test_tokens.py."""

    def __init__(self, keyring: KeyRing, issuer: str) -> None:
        from freya_common.auth_client import TokenVerifier

        self._inner = TokenVerifier(_FakeJwks(keyring.jwks()), issuer)

    async def verify(self, token: str) -> dict:
        return await self._inner.verify(token)


class _FakeAppState:
    def __init__(self, verifier: _FakeVerifier) -> None:
        self.verifier = verifier


class _FakeApp:
    def __init__(self, verifier: _FakeVerifier) -> None:
        self.state = _FakeAppState(verifier)


class _FakeRequest:
    def __init__(self, token: str, verifier: _FakeVerifier) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.app = _FakeApp(verifier)


_ISSUER = "https://freya-auth:8002"


def _token_for_tenant(keyring: KeyRing, tenant_id: str, role: str) -> str:
    token, _ = issue_user_token(
        keyring,
        user_id="usr_ABC123",
        tenant_id=tenant_id,
        role=role,
        permissions=["read:self", "admin:users"],
        issuer=_ISSUER,
        ttl_seconds=900,
    )
    return token


@pytest.fixture
def keyring() -> KeyRing:
    return KeyRing.load(Path("/no/existe"))  # fuerza la clave efímera en memoria


def _force_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # La imagen de test corre con FREYA_AUTH_ENABLED=false (arranque en
    # frío, antes de que exista ninguna cuenta) -- fuerza la rama real de
    # verificación de JWT, que es la que se está probando aquí.
    monkeypatch.setattr(
        deps_module, "get_settings", lambda: Settings(auth_enabled=True)
    )


async def test_admin_principal_rechaza_token_de_otro_tenant(
    keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_auth_enabled(monkeypatch)
    set_tenant("freya")
    token = _token_for_tenant(keyring, tenant_id="otro-tenant", role="admin")
    request = _FakeRequest(token, _FakeVerifier(keyring, _ISSUER))
    with pytest.raises(Forbidden):
        await admin_principal(request)  # type: ignore[arg-type]


async def test_admin_principal_acepta_token_del_mismo_tenant(
    keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_auth_enabled(monkeypatch)
    set_tenant("freya")
    token = _token_for_tenant(keyring, tenant_id="freya", role="admin")
    request = _FakeRequest(token, _FakeVerifier(keyring, _ISSUER))
    claims = await admin_principal(request)  # type: ignore[arg-type]
    assert claims["tenant_id"] == "freya"


async def test_user_principal_rechaza_token_de_otro_tenant(
    keyring: KeyRing, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_auth_enabled(monkeypatch)
    set_tenant("freya")
    token = _token_for_tenant(keyring, tenant_id="otro-tenant", role="user")
    request = _FakeRequest(token, _FakeVerifier(keyring, _ISSUER))
    with pytest.raises(Forbidden):
        await user_principal(request)  # type: ignore[arg-type]
