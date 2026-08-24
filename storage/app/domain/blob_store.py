"""Bytes en volumen (docs/ROADMAP.md Fase 4), en un layout legible como NAS
real: una carpeta por tenant/bucket/key, no un sharding opaco por hash del
id de versión. gestor-db sólo guarda metadatos — el contenido nunca pasa
por la base.

Cada versión se guarda en su propio fichero dentro de la carpeta de su key,
nombrado por su id (`ver_...`): la key puede repetirse entre versiones, el
id de versión distingue cada fichero sin que uno sobrescriba al otro.

Todo el I/O es por streaming (chunks, nunca el objeto entero en memoria de
golpe) -- encontrado en vivo: con `content: bytes` de punta a punta,
`freya-storage` acababa con un RSS de ~256MiB (su propio límite, con swap
real) tras servir unos pocos objetos de varios MiB, cinco veces lo que usa
cualquier otro servicio de la plataforma con exactamente el mismo patrón
FastAPI+asyncpg -- el pico de memoria de un solo PUT/GET grande nunca
bajaba después (CPython/glibc no le devuelven al SO la memoria liberada de
un buffer así de golpe). Escribir/leer en trozos de 1 MiB acota el pico
real a ~1 MiB por petición en vez de al tamaño del objeto entero.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

from freya_common import BadRequest, PayloadTooLarge

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


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


def _path_for(
    data_dir: Path, tenant: str, bucket: str, key: str, version_id: str
) -> Path:
    return _dir_for(data_dir, tenant, bucket, key) / version_id


async def write(
    data_dir: Path,
    tenant: str,
    bucket: str,
    key: str,
    version_id: str,
    chunks: AsyncIterator[bytes],
    *,
    max_bytes: int,
) -> tuple[str, int]:
    """Escribe el blob leyendo `chunks` (p.ej. `request.stream()` de
    FastAPI) sin acumular el cuerpo entero en memoria. `max_bytes` se
    aplica de verdad aquí, no sólo contra la cabecera Content-Length -- un
    cliente que mande un cuerpo más grande sin (o mintiendo en)
    Content-Length se corta a mitad de escritura en vez de agotar RAM.
    Devuelve (sha256_hex, tamaño real escrito)."""
    directory = _dir_for(data_dir, tenant, bucket, key)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / version_id
    hasher = hashlib.sha256()
    size = 0
    handle = await asyncio.to_thread(path.open, "wb")
    try:
        async for chunk in chunks:
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLarge(
                    f"El objeto excede el máximo de {max_bytes} bytes",
                    details={"max_bytes": max_bytes},
                )
            hasher.update(chunk)
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        await asyncio.to_thread(handle.close)
        await asyncio.to_thread(path.unlink, True)  # missing_ok
        raise
    await asyncio.to_thread(handle.close)
    return hasher.hexdigest(), size


async def read(
    data_dir: Path, tenant: str, bucket: str, key: str, version_id: str
) -> AsyncIterator[bytes]:
    """Generador async que lee el blob entero en trozos de 1 MiB."""
    path = _path_for(data_dir, tenant, bucket, key, version_id)
    handle = await asyncio.to_thread(path.open, "rb")
    try:
        while True:
            chunk = await asyncio.to_thread(handle.read, _CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


async def read_range(
    data_dir: Path,
    tenant: str,
    bucket: str,
    key: str,
    version_id: str,
    start: int,
    end: int,
) -> AsyncIterator[bytes]:
    """Generador async de [start, end] inclusive, como pide el header
    Range, en trozos de 1 MiB como mucho."""
    path = _path_for(data_dir, tenant, bucket, key, version_id)

    def _open_and_seek() -> object:
        handle = path.open("rb")
        handle.seek(start)
        return handle

    handle = await asyncio.to_thread(_open_and_seek)
    remaining = end - start + 1
    try:
        while remaining > 0:
            chunk = await asyncio.to_thread(handle.read, min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


def delete(data_dir: Path, tenant: str, bucket: str, key: str, version_id: str) -> None:
    _path_for(data_dir, tenant, bucket, key, version_id).unlink(missing_ok=True)


def size_of(data_dir: Path, tenant: str, bucket: str, key: str, version_id: str) -> int:
    return _path_for(data_dir, tenant, bucket, key, version_id).stat().st_size
