"""app/domain/tenants.py: validación de permisos de proyecto, sin red ni
base (pedido explícito del usuario: storage/monitoring por tenant, y tener
el tenant asignado no implica ningún permiso)."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.domain.tenants import (
    TENANT_GRANTABLE_PERMISSIONS,
    _validate_tenant_permissions,
)


def test_storage_y_monitoring_son_los_unicos_concedibles_por_proyecto() -> None:
    assert set(TENANT_GRANTABLE_PERMISSIONS) == {"storage", "monitoring"}


def test_validate_tenant_permissions_acepta_storage() -> None:
    _validate_tenant_permissions(["read:storage", "write:storage"])


def test_validate_tenant_permissions_acepta_monitoring() -> None:
    _validate_tenant_permissions(["read:monitoring"])


def test_validate_tenant_permissions_rechaza_lo_no_concedible() -> None:
    # git/cicd no se conceden por proyecto -- siguen siendo grants planos
    # (app.domain.users.SERVICE_GRANTS), no algo que quepa en un tenant.
    with pytest.raises(FreyaError) as exc_info:
        _validate_tenant_permissions(["read:git"])
    assert exc_info.value.status_code == 400


def test_validate_tenant_permissions_acepta_lista_vacia() -> None:
    _validate_tenant_permissions([])
