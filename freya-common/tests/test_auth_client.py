"""require_service_access: permiso plano (rol admin) o tenant_grant
(accesos por proyecto -- ver auth/app/domain/tenants.py)."""

from __future__ import annotations

import pytest

from freya_common import FreyaError, require_service_access


def test_pasa_con_permiso_plano() -> None:
    require_service_access({"permissions": ["read:storage"]}, "athenea", "read:storage")


def test_pasa_con_comodin() -> None:
    require_service_access({"permissions": ["*"]}, "athenea", "read:storage")


def test_pasa_con_tenant_grant_del_tenant_pedido() -> None:
    claims = {"permissions": [], "tenant_grants": {"athenea": ["read:storage"]}}
    require_service_access(claims, "athenea", "read:storage")


def test_rechaza_tenant_grant_de_otro_tenant() -> None:
    claims = {"permissions": [], "tenant_grants": {"freya": ["read:storage"]}}
    with pytest.raises(FreyaError) as exc_info:
        require_service_access(claims, "athenea", "read:storage")
    assert exc_info.value.status_code == 403


def test_rechaza_permiso_distinto_en_el_mismo_tenant() -> None:
    claims = {"permissions": [], "tenant_grants": {"athenea": ["read:monitoring"]}}
    with pytest.raises(FreyaError):
        require_service_access(claims, "athenea", "read:storage")


def test_rechaza_sin_nada() -> None:
    with pytest.raises(FreyaError):
        require_service_access({}, "athenea", "read:storage")
