"""Bytes en volumen (docs/ROADMAP.md Fase 4), en un layout legible como NAS
real: una carpeta por tenant/bucket/key, no un sharding opaco por hash del
id de versión. gestor-db sólo guarda metadatos — el contenido nunca pasa
por la base.

Cada versión se guarda en su propio fichero dentro de la carpeta de su key,
nombrado por su id (`ver_...`): la key puede repetirse entre versiones, el
id de versión distingue cada fichero sin que uno sobrescriba al otro.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from freya_common import BadRequest


def _safe_join(data_dir: Path, *parts: str) -> Path:
    """Resuelve data_dir/<parts...> y confirma que el resultado sigue
    dentro de data_dir -- defensa en profundidad contra un bucket o key con
    ".." o una ruta absoluta, la misma técnica que usa cicd para nombres de
    servicio (cicd/app/domain/runner.py:validate_service_name)."""
    root = data_dir.resolve()
    target = data_dir.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        raise BadRequest("bucket o key resuelven fuera del área de datos")
    return target


def _dir_for(data_dir: Path, tenant: str, bucket: str, key: str) -> Path:
    # La key puede traer "/" (p.ej. "{repo}/pack" en git) -- se preserva
    # como subcarpetas reales en vez de aplanarse: es lo que hace que el
    # volumen se lea como un NAS de verdad ("carpeta git", "carpeta
    # secrets"...), no como un espacio de hashes opacos.
    segments = [s for s in key.split("/") if s]
    # Primera barrera: ningún segmento (de bucket o de key) puede ser ".."
    # o ".", ni contener un separador de ruta -- un "b/../secrets" no debe
    # poder terminar escribiendo en la carpeta de otro bucket aunque el
    # resultado final siguiera técnicamente dentro de data_dir. Segunda
    # barrera abajo (_safe_join con resolve()): confirma que el resultado
    # sigue dentro de data_dir pase lo que pase con esta primera.
    for segment in (bucket, *segments):
        if segment in ("", ".", "..") or "/" in segment or "\\" in segment:
            raise BadRequest("bucket o key contienen un segmento de ruta inválido")
    return _safe_join(data_dir, tenant, bucket, *segments)


def write(
    data_dir: Path,
    tenant: str,
    bucket: str,
    key: str,
    version_id: str,
    content: bytes,
) -> tuple[str, int]:
    """Escribe el blob. Devuelve (sha256_hex, tamaño)."""
    directory = _dir_for(data_dir, tenant, bucket, key)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / version_id
    path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    return checksum, len(content)


def read(data_dir: Path, tenant: str, bucket: str, key: str, version_id: str) -> bytes:
    return (_dir_for(data_dir, tenant, bucket, key) / version_id).read_bytes()


def read_range(
    data_dir: Path,
    tenant: str,
    bucket: str,
    key: str,
    version_id: str,
    start: int,
    end: int,
) -> bytes:
    """Lee [start, end] inclusive, como pide el header Range."""
    path = _dir_for(data_dir, tenant, bucket, key) / version_id
    with path.open("rb") as handle:
        handle.seek(start)
        return handle.read(end - start + 1)


def delete(data_dir: Path, tenant: str, bucket: str, key: str, version_id: str) -> None:
    (_dir_for(data_dir, tenant, bucket, key) / version_id).unlink(missing_ok=True)


def size_of(data_dir: Path, tenant: str, bucket: str, key: str, version_id: str) -> int:
    return (_dir_for(data_dir, tenant, bucket, key) / version_id).stat().st_size
