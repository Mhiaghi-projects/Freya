"""Papelera por usuario (app/domain/objects.py: delete_object/list_trash/
restore_object/purge_object) -- pedido explícito del usuario. Un
gestor-db falso en memoria (MockTransport) para poder probar de verdad
el ciclo borrar -> ver en la papelera -> restaurar/purgar, no sólo llamadas
sueltas."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from freya_common import FreyaError, ServiceClient

from app.domain.objects import (
    delete_object,
    get_object_metadata,
    list_trash,
    put_object,
    restore_object,
)


class _FakeGestorDb:
    """Suficiente del DSL de gestor-db (insert/update/delete/query con
    igualdad e is_null) para ejercitar el ciclo completo de la papelera."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def _match(self, row: dict, where: dict) -> bool:
        for field, cond in (where or {}).items():
            if isinstance(cond, dict) and "is_null" in cond:
                if (row.get(field) is None) != cond["is_null"]:
                    return False
            elif isinstance(cond, dict) and "like" in cond:
                needle = cond["like"].rstrip("%")
                if not (row.get(field) or "").startswith(needle):
                    return False
            elif row.get(field) != cond:
                return False
        return True

    def handle(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        table = self.tables.setdefault(body["table"], [])
        if request.url.path == "/query":
            rows = [r for r in table if self._match(r, body.get("where") or {})]
            select = body.get("select")
            if select:
                rows = [{k: r.get(k) for k in select} for r in rows]
            return httpx.Response(200, json={"success": True, "data": {"rows": rows}})
        if request.url.path == "/mutate":
            action = body["action"]
            if action == "insert":
                table.append(dict(body["data"]))
            elif action == "update":
                for r in table:
                    if self._match(r, body.get("where") or {}):
                        r.update(body["data"])
            elif action == "delete":
                self.tables[body["table"]] = [
                    r for r in table if not self._match(r, body.get("where") or {})
                ]
            return httpx.Response(200, json={"success": True, "data": {}})
        raise AssertionError(f"ruta inesperada: {request.url.path}")


@pytest.fixture
def fake_db() -> _FakeGestorDb:
    return _FakeGestorDb()


@pytest.fixture
def client(fake_db: _FakeGestorDb) -> ServiceClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_db.handle))
    return ServiceClient("https://freya-gestor-db:8001", "storage", http)


async def _upload(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb, *, bucket: str, key: str
) -> None:
    buckets = fake_db.tables.setdefault("storage_buckets", [])
    if not any(b["bucket"] == bucket for b in buckets):
        buckets.append({
            "id": f"bkt_{bucket}", "bucket": bucket, "versioning": False,
            "encryption": False, "max_versions": 5, "quota_bytes": 10_000_000_000,
            "deleted_at": None,
        })

    async def body():
        yield b"contenido"

    await put_object(
        client, "freya", tmp_path,
        bucket=bucket, key=key, content_stream=body(),
        content_length_hint=9, max_bytes=10_000_000,
        mime_type="text/plain", metadata="", if_none_match=None,
    )


async def test_borrar_manda_a_la_papelera_de_quien_borra(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb
) -> None:
    await _upload(client, tmp_path, fake_db, bucket="users", key="u1/a.txt")
    await delete_object(
        client, "freya", tmp_path, bucket="users", key="u1/a.txt",
        version_id=None, deleted_by="usr_1",
    )
    trashed = await list_trash(
        client, "freya", bucket="users", deleted_by="usr_1", prefix=None, limit=50, offset=0
    )
    assert len(trashed) == 1
    assert trashed[0]["key"] == "u1/a.txt"

    with pytest.raises(FreyaError) as exc_info:
        await get_object_metadata(client, "freya", bucket="users", key="u1/a.txt", version_id=None)
    assert exc_info.value.status_code == 404


async def test_papelera_es_por_usuario_no_por_bucket(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb
) -> None:
    await _upload(client, tmp_path, fake_db, bucket="project", key="nota.txt")
    await delete_object(
        client, "freya", tmp_path, bucket="project", key="nota.txt",
        version_id=None, deleted_by="usr_1",
    )
    otro = await list_trash(
        client, "freya", bucket="project", deleted_by="usr_2", prefix=None, limit=50, offset=0
    )
    assert otro == []
    mio = await list_trash(
        client, "freya", bucket="project", deleted_by="usr_1", prefix=None, limit=50, offset=0
    )
    assert len(mio) == 1


async def test_restaurar_lo_devuelve_a_su_sitio(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb
) -> None:
    await _upload(client, tmp_path, fake_db, bucket="users", key="u1/a.txt")
    await delete_object(
        client, "freya", tmp_path, bucket="users", key="u1/a.txt",
        version_id=None, deleted_by="usr_1",
    )
    [trashed] = await list_trash(
        client, "freya", bucket="users", deleted_by="usr_1", prefix=None, limit=50, offset=0
    )
    await restore_object(client, "freya", bucket="users", object_id=trashed["id"], user_id="usr_1")
    meta = await get_object_metadata(
        client, "freya", bucket="users", key="u1/a.txt", version_id=None
    )
    assert meta["key"] == "u1/a.txt"


async def test_no_se_puede_restaurar_la_papelera_de_otro(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb
) -> None:
    await _upload(client, tmp_path, fake_db, bucket="users", key="u1/a.txt")
    await delete_object(
        client, "freya", tmp_path, bucket="users", key="u1/a.txt",
        version_id=None, deleted_by="usr_1",
    )
    [trashed] = await list_trash(
        client, "freya", bucket="users", deleted_by="usr_1", prefix=None, limit=50, offset=0
    )
    with pytest.raises(FreyaError) as exc_info:
        await restore_object(
            client, "freya", bucket="users", object_id=trashed["id"], user_id="usr_2"
        )
    assert exc_info.value.status_code == 404


async def test_restaurar_choca_si_ya_hay_algo_en_esa_clave(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb
) -> None:
    await _upload(client, tmp_path, fake_db, bucket="users", key="u1/a.txt")
    await delete_object(
        client, "freya", tmp_path, bucket="users", key="u1/a.txt",
        version_id=None, deleted_by="usr_1",
    )
    [trashed] = await list_trash(
        client, "freya", bucket="users", deleted_by="usr_1", prefix=None, limit=50, offset=0
    )
    # ocupa la clave de nuevo
    await _upload(client, tmp_path, fake_db, bucket="users", key="u1/a.txt")
    with pytest.raises(FreyaError) as exc_info:
        await restore_object(
            client, "freya", bucket="users", object_id=trashed["id"], user_id="usr_1"
        )
    assert exc_info.value.status_code == 409


async def test_deleted_by_none_borra_de_inmediato_sin_papelera(
    client: ServiceClient, tmp_path: Path, fake_db: _FakeGestorDb
) -> None:
    # Llamada de servicio (sin "sub" en el token) -- ej. git limpiando su
    # propio bucket interno: nadie tiene una papelera que lo recupere.
    await _upload(client, tmp_path, fake_db, bucket="git", key="repo/pack.bin")
    await delete_object(
        client, "freya", tmp_path, bucket="git", key="repo/pack.bin",
        version_id=None, deleted_by=None,
    )
    with pytest.raises(FreyaError):
        await get_object_metadata(
            client, "freya", bucket="git", key="repo/pack.bin", version_id=None
        )
