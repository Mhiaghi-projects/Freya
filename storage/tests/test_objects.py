"""Un objeto subido con Content-Type: application/json debe descargarse tal
cual, sin que EnvelopeMiddleware lo confunda con una respuesta de la propia
API de storage y lo envuelva en {success, data, meta} (bug real que sufrió
git subiendo refs.json, ver git/README.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from freya_common import NO_ENVELOPE_HEADER

from app.api import objects as objects_api
from app.deps import authenticated
from app.main import app

_META = {
    "bucket": "b",
    "key": "refs.json",
    "version_id": "ver_1",
    "status": "ACTIVE",
    "size": 14,
    "mime_type": "application/json",
    "etag": "deadbeef",
    "metadata": "",
}
_BODY = b'{"head": "x"}'


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_get_object_metadata(*_args: object, **_kwargs: object) -> dict:
        return _META

    async def fake_read(*_args: object, **_kwargs: object):
        yield _BODY

    async def fake_read_range(*_args: object, **_kwargs: object):
        yield _BODY[:5]

    monkeypatch.setattr(objects_api, "get_object_metadata", fake_get_object_metadata)
    monkeypatch.setattr(objects_api.blob_store, "read", fake_read)
    monkeypatch.setattr(objects_api.blob_store, "read_range", fake_read_range)
    app.dependency_overrides[authenticated] = lambda: {
        "service": "test",
        "permissions": ["*"],
    }
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(authenticated, None)


def test_descarga_json_no_se_envuelve(client: TestClient) -> None:
    response = client.get("/storage/b/refs.json")
    assert response.status_code == 200
    assert response.content == _BODY


def test_descarga_json_no_filtra_la_cabecera_de_opt_out(client: TestClient) -> None:
    response = client.get("/storage/b/refs.json")
    assert NO_ENVELOPE_HEADER not in response.headers


def test_head_no_filtra_la_cabecera_de_opt_out(client: TestClient) -> None:
    response = client.head("/storage/b/refs.json")
    assert response.status_code == 200
    assert NO_ENVELOPE_HEADER not in response.headers


def test_range_json_no_se_envuelve(client: TestClient) -> None:
    response = client.get(
        "/storage/b/refs.json", headers={"Range": "bytes=0-4"}
    )
    assert response.status_code == 206
    assert response.content == _BODY[:5]
