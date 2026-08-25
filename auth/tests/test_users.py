"""Modelo de permisos de app/domain/users.py, sin red ni base. storage,
monitoring, git, cicd y project-manager ya NO se conceden aquí de forma
global (pedido explícito del usuario: "asimismo con el git, Drive, CI/CD,
Proyectos") -- todos se conceden por proyecto/tenant, ver test_tenants.py.
SERVICE_GRANTS queda vacío a propósito, el mecanismo se conserva por si
algún futuro acceso realmente necesitara ser global."""

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


def test_admin_si_tiene_todo_por_defecto() -> None:
    # El admin sigue sin estar acotado por tenant para storage/monitoring
    # (pedido explícito del usuario: "admin sólo tiene vista global de
    # Freya" es la única restricción, aplicada en runtime -- ver
    # storage/app/deps.py y gestor-monitoring/app/api/monitoring.py, no
    # aquí) -- su acceso plano de siempre sigue intacto para los 5
    # servicios que ahora son por-proyecto para una cuenta "user".
    perms = permissions_for_role("admin")
    for p in (
        "read:storage", "write:storage", "read:monitoring", "write:monitoring",
        "read:git", "write:git", "read:cicd", "write:cicd",
        "read:project-manager", "write:project-manager",
    ):
        assert p in perms


def test_service_grants_queda_vacio() -> None:
    # storage/monitoring/git/cicd/project-manager se movieron todos a
    # TENANT_GRANTABLE_PERMISSIONS (app.domain.tenants) -- no queda nada
    # que conceder de forma global hoy.
    assert SERVICE_GRANTS == {}


def test_full_permissions_filtra_extra_permissions_no_concedibles() -> None:
    # Hallazgo de una revisión de seguridad: storage/monitoring vivían en
    # extra_permissions antes de pasar a ser por-tenant (y ahora también
    # git/cicd/project-manager). Si una fila vieja de la base conservara
    # uno de esos permisos, full_permissions() ya no debe reflejarlo en el
    # JWT -- si no, esa cuenta tendría acceso plano a TODOS los tenants,
    # no sólo a los concedidos en user_tenant_grants.
    perms = full_permissions("user", ["read:storage", "write:git", "read:self"])
    assert "read:storage" not in perms
    assert "write:git" not in perms
    assert "read:self" in perms


def test_validate_extra_permissions_no_acepta_nada_ya() -> None:
    # Con SERVICE_GRANTS vacío, ningún permiso de servicio es concedible
    # de forma global -- todo pasa por user_tenant_grants ahora.
    with pytest.raises(FreyaError) as exc_info:
        _validate_extra_permissions(["read:git"])
    assert exc_info.value.status_code == 400


async def test_update_theme_rechaza_tema_desconocido() -> None:
    # La validación corre antes de tocar la base -- client=None nunca se usa
    # si theme es inválido.
    with pytest.raises(FreyaError) as exc_info:
        await update_theme(None, "acme", user_id="usr_1", theme="neon")
    assert exc_info.value.status_code == 400
    assert exc_info.value.details["known_themes"] == THEMES
