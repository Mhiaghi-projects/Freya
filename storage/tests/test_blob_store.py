"""Pruebas unitarias puras de app/domain/blob_store.py — sin gestor-db."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from freya_common import BadRequest, PayloadTooLarge

from app.domain import blob_store

_MAX = 10 * 1024 * 1024


async def _chunks(data: bytes, *, chunk_size: int = 4) -> AsyncIterator[bytes]:
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]


async def _collect(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([chunk async for chunk in stream])


async def test_write_read_roundtrip(tmp_path: Path) -> None:
    checksum, size = await blob_store.write(
        tmp_path,
        "freya",
        "backups",
        "database/freya.dump",
        "ver_abc123",
        _chunks(b"hola mundo"),
        max_bytes=_MAX,
    )
    assert size == len(b"hola mundo")
    assert len(checksum) == 64  # sha256 hex

    body = await _collect(
        blob_store.read(
            tmp_path, "freya", "backups", "database/freya.dump", "ver_abc123"
        )
    )
    assert body == b"hola mundo"


async def test_write_crea_una_carpeta_legible_por_bucket_y_key(tmp_path: Path) -> None:
    # La key con "/" se preserva como subcarpetas reales -- lo que hace que
    # el volumen se lea como un NAS de verdad (una carpeta por servicio),
    # no como un espacio de hashes opacos.
    await blob_store.write(
        tmp_path,
        "freya",
        "git",
        "mi-repo/pack",
        "ver_abc123",
        _chunks(b"x"),
        max_bytes=_MAX,
    )
    assert (tmp_path / "freya" / "git" / "mi-repo" / "pack" / "ver_abc123").is_file()


async def test_read_range_devuelve_el_tramo_pedido(tmp_path: Path) -> None:
    await blob_store.write(
        tmp_path, "freya", "b", "k", "ver_range", _chunks(b"0123456789"), max_bytes=_MAX
    )
    body = await _collect(
        blob_store.read_range(tmp_path, "freya", "b", "k", "ver_range", 2, 5)
    )
    assert body == b"2345"


async def test_write_corta_al_superar_max_bytes(tmp_path: Path) -> None:
    # Aunque Content-Length mienta o falte, el límite se aplica de verdad
    # aquí, byte a byte, no sólo en la cabecera -- y no deja un fichero
    # parcial/sobredimensionado a medio escribir.
    with pytest.raises(PayloadTooLarge):
        await blob_store.write(
            tmp_path,
            "freya",
            "b",
            "k",
            "ver_grande",
            _chunks(b"0123456789"),
            max_bytes=5,
        )
    assert not (tmp_path / "freya" / "b" / "k" / "ver_grande").exists()


def test_delete_borra_el_fichero(tmp_path: Path) -> None:
    (tmp_path / "freya" / "b" / "k").mkdir(parents=True)
    (tmp_path / "freya" / "b" / "k" / "ver_del").write_bytes(b"borrame")
    blob_store.delete(tmp_path, "freya", "b", "k", "ver_del")
    assert not (tmp_path / "freya" / "b" / "k" / "ver_del").exists()


def test_delete_de_inexistente_no_falla(tmp_path: Path) -> None:
    blob_store.delete(tmp_path, "freya", "b", "k", "ver_no_existe")


def test_size_of(tmp_path: Path) -> None:
    (tmp_path / "freya" / "b" / "k").mkdir(parents=True)
    (tmp_path / "freya" / "b" / "k" / "ver_size").write_bytes(b"12345")
    assert blob_store.size_of(tmp_path, "freya", "b", "k", "ver_size") == 5


@pytest.mark.parametrize(
    "bucket,key",
    [
        ("../../etc", "passwd"),
        ("b", "../../../etc/passwd"),
        ("b", "../secrets"),
    ],
)
async def test_bucket_o_key_con_recorrido_de_ruta_lanza(
    tmp_path: Path, bucket: str, key: str
) -> None:
    with pytest.raises(BadRequest):
        await blob_store.write(
            tmp_path, "freya", bucket, key, "ver_x", _chunks(b"x"), max_bytes=_MAX
        )


def test_delete_tenant_borra_todo_su_directorio(tmp_path: Path) -> None:
    (tmp_path / "athenea" / "project" / "nota.txt").mkdir(parents=True)
    (tmp_path / "athenea" / "project" / "nota.txt" / "ver_1").write_bytes(b"hola")
    (tmp_path / "freya" / "users" / "u1").mkdir(parents=True)
    blob_store.delete_tenant(tmp_path, "athenea")
    assert not (tmp_path / "athenea").exists()
    assert (tmp_path / "freya").exists()  # otros tenants intactos


def test_delete_tenant_de_inexistente_no_falla(tmp_path: Path) -> None:
    blob_store.delete_tenant(tmp_path, "no-existe")


@pytest.mark.parametrize("tenant", ["..", "../etc", "a/b", "a\\b"])
def test_delete_tenant_con_recorrido_de_ruta_lanza(tmp_path: Path, tenant: str) -> None:
    with pytest.raises(BadRequest):
        blob_store.delete_tenant(tmp_path, tenant)
