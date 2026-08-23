"""FastAPI/Starlette resuelve por orden de registro cuando dos rutas podrían
encajar con la misma petición. `{key:path}` es un converter "greedy": sin el
orden correcto, "/storage/b/foo/versions" se leería como key="foo/versions"
en vez de resolver al listado de versiones de "foo" — y "/storage/buckets"
se leería como bucket="buckets" si el router de objetos se registrara antes
que el de buckets. Esto ya pasó una vez con secrets/audit-logs; se queda
como regresión para storage también."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import buckets as buckets_api
from app.api import objects as objects_api
from app.api.objects import router as objects_router
from app.deps import authenticated
from app.main import app


def test_versions_se_registra_antes_que_el_key_generico() -> None:
    get_paths = [r.path for r in objects_router.routes if "GET" in r.methods]
    specific = get_paths.index("/storage/{bucket}/{key:path}/versions")
    generic = get_paths.index("/storage/{bucket}/{key:path}")
    assert specific < generic


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # No hay gestor-db real en el contenedor de tests: se sustituye la capa
    # de dominio por dobles que dejan ver, sin ambigüedad, qué handler
    # respondió de verdad a la petición ASGI (el routing real, no una
    # introspección de app.routes).
    async def fake_list_buckets(*_args: object, **_kwargs: object) -> list[dict]:
        return [{"bucket": "gano-buckets-router"}]

    async def fake_list_objects(*_args: object, **_kwargs: object) -> list[dict]:
        return [{"key": "gano-objects-router"}]

    monkeypatch.setattr(buckets_api, "list_buckets", fake_list_buckets)
    monkeypatch.setattr(objects_api, "list_objects", fake_list_objects)
    app.dependency_overrides[authenticated] = lambda: {
        "service": "test",
        "permissions": ["*"],
    }
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(authenticated, None)


def test_storage_buckets_no_se_confunde_con_bucket_generico(
    client: TestClient,
) -> None:
    # Si objects.py se registrara antes que buckets.py, esta petición caería
    # en list_bucket_objects (bucket="buckets") en vez de en list_buckets.
    response = client.get("/storage/buckets")
    assert response.status_code == 200
    assert response.json()["data"] == [{"bucket": "gano-buckets-router"}]
