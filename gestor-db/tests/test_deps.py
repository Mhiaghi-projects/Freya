"""require_db_access (app/deps.py): gestor-db "como un RDS" para proyectos
propios -- un JWT de servicio sigue siendo de confianza total para
cualquier tenant que declare (como siempre); un JWT de usuario necesita
un tenant_grant real de "database" (read:database/write:database), mismo
criterio que storage/git/cicd/project-manager."""

from __future__ import annotations

import pytest
from freya_common import FreyaError

from app.deps import Caller, require_db_access


def test_servicio_usa_su_confianza_total_sin_grants() -> None:
    caller = Caller(tenant="athenea", service="storage", is_service=True)
    claims = {"service": "storage", "permissions": ["*"]}
    require_db_access(claims, caller, "write:database")


def test_usuario_con_grant_explicito_puede_acceder() -> None:
    caller = Caller(tenant="athenea", service="", is_service=False)
    claims = {
        "role": "user", "permissions": [],
        "tenant_grants": {"athenea": ["read:database"]},
    }
    require_db_access(claims, caller, "read:database")


def test_usuario_sin_grant_rechazado() -> None:
    caller = Caller(tenant="athenea", service="", is_service=False)
    with pytest.raises(FreyaError) as exc_info:
        require_db_access({"role": "user", "permissions": []}, caller, "read:database")
    assert exc_info.value.status_code == 403


def test_usuario_con_grant_de_otro_tenant_no_alcanza() -> None:
    caller = Caller(tenant="athenea", service="", is_service=False)
    claims = {
        "role": "user", "permissions": [],
        "tenant_grants": {"freya": ["read:database"]},
    }
    with pytest.raises(FreyaError):
        require_db_access(claims, caller, "read:database")


def test_admin_usa_su_permiso_plano_para_cualquier_tenant() -> None:
    # A diferencia de storage/monitoring (que restringen admin sólo a
    # "freya"), aquí NO se pidió esa restricción extra -- mismo criterio
    # que git/cicd/project-manager: el rol admin trae "read:database"/
    # "write:database" planos (ROLE_PERMISSIONS), así que
    # require_service_access lo deja pasar sin necesitar un tenant_grant
    # explícito, para cualquier tenant.
    caller = Caller(tenant="athenea", service="", is_service=False)
    claims = {"role": "admin", "permissions": ["read:database", "write:database"]}
    require_db_access(claims, caller, "read:database")
