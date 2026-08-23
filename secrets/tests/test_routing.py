"""FastAPI resuelve por orden de registro cuando dos rutas podrían encajar
con la misma petición. "/audit-logs" y "/{key:path}/versions" se confunden
con "/{key:path}" si el genérico se registra antes -- esto pasó de verdad
con audit-logs, se queda como regresión. {key:path} (no {key}) además:
los secretos de arranque importados usan namespacing jerárquico
(bootstrap/storage/api_secret, ver infra/scripts/import_bootstrap_secrets.py)."""

from __future__ import annotations

from app.api.secrets import router


def test_audit_logs_se_registra_antes_que_el_key_generico() -> None:
    get_paths = [r.path for r in router.routes if "GET" in r.methods]
    specific = get_paths.index("/secrets/{namespace}/audit-logs")
    generic = get_paths.index("/secrets/{namespace}/{key:path}")
    assert specific < generic


def test_versions_se_registra_antes_que_el_key_generico() -> None:
    get_paths = [r.path for r in router.routes if "GET" in r.methods]
    specific = get_paths.index("/secrets/{namespace}/{key:path}/versions")
    generic = get_paths.index("/secrets/{namespace}/{key:path}")
    assert specific < generic
