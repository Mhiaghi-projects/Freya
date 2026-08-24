"""app/domain/provisioning.py: aplica migraciones + crea el bucket
"project" de un tenant nuevo, sin red real (httpx.MockTransport, mismo
patrón que freya-common/tests/test_http.py)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from freya_common import ServiceClient

from app.domain.provisioning import PROJECT_BUCKET, provision_tenant


def _client(handler) -> ServiceClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ServiceClient("https://freya-gestor-db:8001", "storage", http)


async def test_aplica_migraciones_y_crea_el_bucket_project(tmp_path: Path) -> None:
    (tmp_path / "0001_init.sql").write_text("CREATE TABLE storage_buckets ();")
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/migrations":
            return httpx.Response(200, json={"success": True, "data": {"applied": []}})
        if request.url.path == "/query":
            return httpx.Response(200, json={"success": True, "data": {"rows": []}})
        if request.url.path == "/mutate":
            return httpx.Response(201, json={"success": True, "data": {"id": "buk_1"}})
        raise AssertionError(f"llamada inesperada: {request.url.path}")

    client = _client(handler)
    result = await provision_tenant(
        client,
        "athenea",
        migrations_dir=tmp_path,
        default_max_versions=5,
        default_quota_bytes=10 * 1024 * 1024 * 1024,
    )
    assert result == {"tenant": "athenea", "bucket": PROJECT_BUCKET}
    assert ("POST", "/migrations") in calls
    assert ("POST", "/mutate") in calls


async def test_tolera_que_el_bucket_project_ya_exista(tmp_path: Path) -> None:
    (tmp_path / "0001_init.sql").write_text("CREATE TABLE storage_buckets ();")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/migrations":
            return httpx.Response(200, json={"success": True, "data": {"applied": []}})
        if request.url.path == "/query":
            # create_bucket comprueba primero si ya existe.
            return httpx.Response(
                200, json={"success": True, "data": {"rows": [{"id": "buk_1"}]}}
            )
        raise AssertionError(f"llamada inesperada: {request.url.path}")

    client = _client(handler)
    result = await provision_tenant(
        client,
        "athenea",
        migrations_dir=tmp_path,
        default_max_versions=5,
        default_quota_bytes=10 * 1024 * 1024 * 1024,
    )
    assert result == {"tenant": "athenea", "bucket": PROJECT_BUCKET}
