"""app/domain/tenants.py: validación de permisos de proyecto, sin red ni
base (pedido explícito del usuario: los 5 servicios combinables --
storage, monitoring, git, cicd, project-manager -- son por tenant, y
tener el tenant asignado no implica ningún permiso)."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.domain.tenants import (
    CONTROL_PLANE_TENANT,
    TENANT_GRANTABLE_PERMISSIONS,
    delete_tenant,
    validate_tenant_permissions,
)


def test_los_seis_servicios_combinables_son_concedibles_por_proyecto() -> None:
    assert set(TENANT_GRANTABLE_PERMISSIONS) == {
        "storage", "monitoring", "git", "cicd", "project-manager", "database",
    }


def test_validate_tenant_permissions_acepta_storage() -> None:
    validate_tenant_permissions(["read:storage", "write:storage"])


def test_validate_tenant_permissions_acepta_monitoring() -> None:
    validate_tenant_permissions(["read:monitoring"])


def test_validate_tenant_permissions_acepta_git_cicd_project_manager() -> None:
    validate_tenant_permissions(["read:git", "write:cicd", "read:project-manager"])


def test_validate_tenant_permissions_acepta_database() -> None:
    validate_tenant_permissions(["read:database", "write:database"])


def test_validate_tenant_permissions_rechaza_lo_no_concedible() -> None:
    # admin:git nunca es un grant que se conceda por proyecto -- es cosa
    # de administración de verdad.
    with pytest.raises(FreyaError) as exc_info:
        validate_tenant_permissions(["admin:git"])
    assert exc_info.value.status_code == 400


def test_validate_tenant_permissions_acepta_lista_vacia() -> None:
    validate_tenant_permissions([])


async def test_delete_tenant_nunca_borra_freya() -> None:
    # La validación corre antes de tocar la base -- client=None nunca se
    # usa si el tenant es "freya" (borrarlo se llevaría toda la
    # plataforma, no un proyecto).
    with pytest.raises(FreyaError) as exc_info:
        await delete_tenant(None, CONTROL_PLANE_TENANT)
    assert exc_info.value.status_code == 400
