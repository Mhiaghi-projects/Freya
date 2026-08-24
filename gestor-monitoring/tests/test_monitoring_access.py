"""_require_project_access (app/api/monitoring.py): admin sólo ve Freya
(pedido explícito del usuario); un usuario normal necesita un
tenant_grant de monitoring para el proyecto pedido."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.api.monitoring import _require_project_access


def test_admin_puede_ver_freya() -> None:
    _require_project_access({"role": "admin", "permissions": []}, "freya", "read:monitoring")


def test_admin_no_puede_ver_otro_proyecto() -> None:
    with pytest.raises(FreyaError) as exc_info:
        _require_project_access(
            {"role": "admin", "permissions": []}, "athenea", "read:monitoring"
        )
    assert exc_info.value.status_code == 403


def test_user_sin_grant_no_puede_ver_nada() -> None:
    with pytest.raises(FreyaError):
        _require_project_access({"role": "user", "permissions": []}, "freya", "read:monitoring")


def test_user_con_grant_ve_su_proyecto() -> None:
    claims = {
        "role": "user",
        "permissions": [],
        "tenant_grants": {"athenea": ["read:monitoring"]},
    }
    _require_project_access(claims, "athenea", "read:monitoring")


def test_user_con_grant_de_un_proyecto_no_ve_otro() -> None:
    claims = {
        "role": "user",
        "permissions": [],
        "tenant_grants": {"athenea": ["read:monitoring"]},
    }
    with pytest.raises(FreyaError):
        _require_project_access(claims, "freya", "read:monitoring")
