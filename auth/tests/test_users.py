"""Modelo de permisos de app/domain/users.py, sin red ni base (pedido
explícito del usuario: storage.read/write nunca automático para 'user',
sólo por grant explícito de un admin, igual que git/cicd/monitoring)."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.domain.users import (
    SERVICE_GRANTS,
    THEMES,
    _validate_extra_permissions,
    full_permissions,
    permissions_for_role,
    update_theme,
)


def test_user_no_tiene_storage_por_defecto() -> None:
    perms = permissions_for_role("user")
    assert "read:storage" not in perms
    assert "write:storage" not in perms


def test_admin_si_tiene_storage_por_defecto() -> None:
    perms = permissions_for_role("admin")
    assert "read:storage" in perms
    assert "write:storage" in perms


def test_storage_es_un_grant_concedible() -> None:
    assert SERVICE_GRANTS["storage"] == ["read:storage", "write:storage"]


def test_conceder_storage_a_un_user_se_lo_da() -> None:
    perms = full_permissions("user", ["read:storage", "write:storage"])
    assert "read:storage" in perms
    assert "write:storage" in perms


def test_user_sin_grant_de_storage_no_lo_tiene() -> None:
    perms = full_permissions("user", [])
    assert "read:storage" not in perms
    assert "write:storage" not in perms


def test_validate_extra_permissions_acepta_storage() -> None:
    _validate_extra_permissions(["read:storage", "write:storage"])


def test_validate_extra_permissions_rechaza_lo_no_concedible() -> None:
    with pytest.raises(FreyaError) as exc_info:
        _validate_extra_permissions(["admin:users"])
    assert exc_info.value.status_code == 400


async def test_update_theme_rechaza_tema_desconocido() -> None:
    # La validación corre antes de tocar la base -- client=None nunca se usa
    # si theme es inválido.
    with pytest.raises(FreyaError) as exc_info:
        await update_theme(None, "acme", user_id="usr_1", theme="neon")
    assert exc_info.value.status_code == 400
    assert exc_info.value.details["known_themes"] == THEMES
