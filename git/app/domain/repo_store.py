"""Persistencia de repos bare en storage.

El contenedor de git no guarda estado propio (tarea git-02 del backlog):
cada repo son 2-3 objetos en el bucket "git" del tenant — el pack
consolidado y un snapshot de refs — nunca uno por objeto git suelto
(storage no está pensado para miles de ficheros diminutos por bucket, ver
storage/README.md). Antes de operar con el binario real de git se
materializa un repo bare efímero en `scratch_dir`; después de cualquier
operación que escriba (receive-pack) se vuelve a empaquetar y se sube.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from freya_common import FreyaError, ServiceClient

from app.config import get_settings
from app.domain import git_ops

_PACK_KEY = "pack"
_REFS_KEY = "refs.json"


async def ensure_bucket(client: ServiceClient, tenant: str) -> None:
    # storage no expone un GET de un solo bucket (sólo listado, PUT, DELETE
    # y /usage) -- crear y tratar "ya existe" como éxito es la única forma
    # idempotente de asegurar el bucket sin listar todos los del tenant.
    bucket = get_settings().git_bucket
    try:
        await client.put(
            f"/storage/buckets/{bucket}",
            tenant=tenant,
            json={"versioning": True, "encryption": False},
        )
    except FreyaError as exc:
        if exc.status_code != 409:
            raise


def workdir_for(tenant: str, repo_name: str) -> Path:
    return get_settings().scratch_dir / tenant / repo_name


async def materialize(
    client: ServiceClient, tenant: str, repo_name: str, default_branch: str
) -> Path:
    """Reconstruye el repo bare a partir de storage. Vacío (sin commits) si
    el repo aún no tiene ningún push."""
    workdir = workdir_for(tenant, repo_name)
    if workdir.exists():
        shutil.rmtree(workdir)
    await git_ops.init_bare(workdir, default_branch)

    bucket = get_settings().git_bucket
    try:
        pack_resp = await client.get(
            f"/storage/{bucket}/{repo_name}/{_PACK_KEY}", tenant=tenant
        )
    except FreyaError as exc:
        if exc.status_code == 404:
            return workdir  # repo vacío: nada más que materializar
        raise

    await git_ops.index_pack(workdir, pack_resp.content)

    try:
        refs_resp = await client.get(
            f"/storage/{bucket}/{repo_name}/{_REFS_KEY}", tenant=tenant
        )
    except FreyaError as exc:
        if exc.status_code == 404:
            return workdir
        raise

    refs = json.loads(refs_resp.content)
    for refname, sha in refs.get("refs", {}).items():
        await git_ops.write_ref(workdir, refname, sha)
    head = refs.get("head")
    if head:
        await git_ops.run_git(["symbolic-ref", "HEAD", head], cwd=workdir)
    return workdir


async def persist(
    client: ServiceClient, tenant: str, repo_name: str, workdir: Path
) -> None:
    """Empaqueta el estado actual de `workdir` y lo sube a storage."""
    bucket = get_settings().git_bucket
    pack_path = await git_ops.repack(workdir)
    if pack_path is not None:
        await client.put(
            f"/storage/{bucket}/{repo_name}/{_PACK_KEY}",
            tenant=tenant,
            content=pack_path.read_bytes(),
            headers={"Content-Type": "application/x-git-packed-objects"},
        )

    refs = dict(await git_ops.for_each_ref(workdir))
    head = await git_ops.symbolic_ref_head(workdir)
    payload: dict[str, Any] = {"head": head, "refs": refs}
    await client.put(
        f"/storage/{bucket}/{repo_name}/{_REFS_KEY}",
        tenant=tenant,
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def cleanup(workdir: Path) -> None:
    shutil.rmtree(workdir, ignore_errors=True)


async def delete_from_storage(
    client: ServiceClient, tenant: str, repo_name: str
) -> None:
    bucket = get_settings().git_bucket
    for key in (_PACK_KEY, _REFS_KEY):
        try:
            await client.delete(f"/storage/{bucket}/{repo_name}/{key}", tenant=tenant)
        except FreyaError as exc:
            if exc.status_code != 404:
                raise
