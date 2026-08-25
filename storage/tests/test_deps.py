"""require_storage_access (app/deps.py): hallazgo de una revisión de
seguridad -- un admin no debe quedar habilitado para CUALQUIER tenant
sólo por tener el permiso plano; sólo su propio tenant ("freya") usa el
acceso plano, cualquier otro proyecto exige el mismo tenant_grant
explícito que a una cuenta "user" (consistente con gestor-monitoring)."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.deps import require_storage_access


def test_admin_usa_su_acceso_plano_en_freya() -> None:
    require_storage_access({"role": "admin", "permissions": ["read:storage"]}, "freya", "read:storage")


def test_admin_sin_grant_no_puede_ver_otro_proyecto() -> None:
    with pytest.raises(FreyaError) as exc_info:
        require_storage_access(
            {"role": "admin", "permissions": ["read:storage"]}, "athenea", "read:storage"
        )
    assert exc_info.value.status_code == 403


def test_admin_con_grant_explicito_si_puede_ver_otro_proyecto() -> None:
    claims = {
        "role": "admin", "permissions": ["read:storage"],
        "tenant_grants": {"athenea": ["read:storage"]},
    }
    require_storage_access(claims, "athenea", "read:storage")


def test_user_sigue_usando_el_camino_normal_de_tenant_grants() -> None:
    claims = {"role": "user", "permissions": [], "tenant_grants": {"athenea": ["read:storage"]}}
    require_storage_access(claims, "athenea", "read:storage")


def test_user_sin_grant_rechazado() -> None:
    with pytest.raises(FreyaError):
        require_storage_access({"role": "user", "permissions": []}, "freya", "read:storage")
