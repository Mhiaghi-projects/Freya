"""Pruebas unitarias puras de app/domain/blob_store.py — sin gestor-db."""

from __future__ import annotations

from pathlib import Path

import pytest
from freya_common import BadRequest

from app.domain import blob_store


def test_write_read_roundtrip(tmp_path: Path) -> None:
    checksum, size = blob_store.write(
        tmp_path, "freya", "backups", "database/freya.dump", "ver_abc123", b"hola mundo"
    )
    assert size == len(b"hola mundo")
    assert len(checksum) == 64  # sha256 hex

    assert (
        blob_store.read(tmp_path, "freya", "backups", "database/freya.dump", "ver_abc123")
        == b"hola mundo"
    )


def test_write_crea_una_carpeta_legible_por_bucket_y_key(tmp_path: Path) -> None:
    # La key con "/" se preserva como subcarpetas reales -- lo que hace que
    # el volumen se lea como un NAS de verdad (una carpeta por servicio),
    # no como un espacio de hashes opacos.
    blob_store.write(tmp_path, "freya", "git", "mi-repo/pack", "ver_abc123", b"x")
    assert (tmp_path / "freya" / "git" / "mi-repo" / "pack" / "ver_abc123").is_file()


def test_read_range_devuelve_el_tramo_pedido(tmp_path: Path) -> None:
    blob_store.write(tmp_path, "freya", "b", "k", "ver_range", b"0123456789")
    assert blob_store.read_range(tmp_path, "freya", "b", "k", "ver_range", 2, 5) == b"2345"


def test_delete_borra_el_fichero(tmp_path: Path) -> None:
    blob_store.write(tmp_path, "freya", "b", "k", "ver_del", b"borrame")
    blob_store.delete(tmp_path, "freya", "b", "k", "ver_del")
    assert not (tmp_path / "freya" / "b" / "k" / "ver_del").exists()


def test_delete_de_inexistente_no_falla(tmp_path: Path) -> None:
    blob_store.delete(tmp_path, "freya", "b", "k", "ver_no_existe")


def test_size_of(tmp_path: Path) -> None:
    blob_store.write(tmp_path, "freya", "b", "k", "ver_size", b"12345")
    assert blob_store.size_of(tmp_path, "freya", "b", "k", "ver_size") == 5


@pytest.mark.parametrize(
    "bucket,key",
    [
        ("../../etc", "passwd"),
        ("b", "../../../etc/passwd"),
        ("b", "../secrets"),
    ],
)
def test_bucket_o_key_con_recorrido_de_ruta_lanza(
    tmp_path: Path, bucket: str, key: str
) -> None:
    with pytest.raises(BadRequest):
        blob_store.write(tmp_path, "freya", bucket, key, "ver_x", b"x")
