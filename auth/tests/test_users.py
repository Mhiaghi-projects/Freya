"""Modelo de permisos de app/domain/users.py, sin red ni base. storage y
monitoring ya NO se conceden aquí de forma global (pedido explícito del
usuario: se conceden por proyecto/tenant -- ver test_tenants.py); sólo
git/cicd/project-manager siguen siendo grants planos."""

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
    # El admin sigue sin estar acotado por tenant (pedido explícito del
    # usuario: "admin sólo tiene vista global de Freya", ver
    # app.domain.tenants.py) -- su acceso a storage/monitoring sigue plano.
    perms = permissions_for_role("admin")
    assert "read:storage" in perms
    assert "write:storage" in perms
    assert "read:monitoring" in perms
    assert "write:monitoring" in perms


def test_storage_y_monitoring_ya_no_son_grants_planos() -> None:
    assert "storage" not in SERVICE_GRANTS
    assert "monitoring" not in SERVICE_GRANTS


def test_git_cicd_project_manager_siguen_siendo_grants_planos() -> None:
    assert set(SERVICE_GRANTS) == {"git", "cicd", "project-manager"}


def test_full_permissions_filtra_extra_permissions_no_concedibles() -> None:
    # Hallazgo de una revisión de seguridad: storage/monitoring vivían en
    # extra_permissions antes de pasar a ser por-tenant. Si una fila vieja
    # de la base conservara uno de esos permisos, full_permissions() ya no
    # debe reflejarlo en el JWT -- si no, esa cuenta tendría acceso plano a
    # TODOS los tenants, no sólo a los concedidos en user_tenant_grants.
    perms = full_permissions("user", ["read:storage", "write:storage", "read:git"])
    assert "read:storage" not in perms
    assert "write:storage" not in perms
    assert "read:git" in perms


def test_validate_extra_permissions_ya_no_acepta_storage() -> None:
    # Antes esto pasaba (storage era un grant plano); ahora storage vive en
    # user_tenant_grants, no en extra_permissions.
    with pytest.raises(FreyaError) as exc_info:
        _validate_extra_permissions(["read:storage", "write:storage"])
    assert exc_info.value.status_code == 400


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
