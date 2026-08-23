"""Lectura de historial sobre un repo bare ya materializado
(docs/freya-api-contract.md §6.3, §6.4, §6.6). Todo pasa por el binario
real de git — nunca se reimplementa el modelo de objetos.

Las tags creadas por la API son siempre anotadas (`git tag -a`): el mensaje
y el tagger quedan en el propio objeto tag de git, sin necesidad de un
canal aparte para esos metadatos.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from freya_common import Conflict, NotFound, UnprocessableEntity

from app.domain.git_ops import GitError, run_git

_SEP = "\x1f"  # separador de campo: no aparece en mensajes de commit normales
_TAG_NAME_RE = re.compile(r"^v\d+\.\d+\.\d+(-[a-z0-9.]+)?$")
# No explotable hoy (argv en forma de lista, nunca shell=True; el prefijo
# "refs/heads/" impide que un nombre con "-" al frente se lea como flag) --
# pero repo_name (RepoCreate) y el nombre de tag (validate_tag_name, abajo)
# sí se validan con regex en el borde como segunda línea de defensa, y el
# nombre de rama era la única excepción, confiando sólo en que git rechace
# un ref-name inválido. Aproximación simplificada de `git check-ref-format`.
_BRANCH_NAME_RE = re.compile(r"^(?!-)(?!.*\.\.)(?!.*[./]$)[A-Za-z0-9][A-Za-z0-9._/-]*$")


def validate_branch_name(name: str) -> None:
    if not _BRANCH_NAME_RE.match(name):
        raise UnprocessableEntity(
            f"'{name}' no es un nombre de rama válido",
            details={"pattern": _BRANCH_NAME_RE.pattern},
        )


async def _rev_parse(workdir: Path, ref: str) -> str:
    try:
        output = await run_git(
            ["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=workdir
        )
    except GitError as exc:
        raise NotFound(f"'{ref}' no existe en el repositorio") from exc
    return output.decode().strip()


async def list_branches(workdir: Path, default_branch: str) -> list[dict[str, Any]]:
    fmt = f"%(refname:short){_SEP}%(objectname){_SEP}%(committerdate:unix)"
    output = await run_git(
        ["for-each-ref", "refs/heads", f"--format={fmt}"], cwd=workdir
    )
    branches = []
    for line in output.decode().strip().splitlines():
        if not line:
            continue
        name, sha, ts = line.split(_SEP)
        branches.append(
            {
                "name": name,
                "head_commit": sha,
                "is_default": name == default_branch,
                "protected": name == default_branch,
                "created_at": int(ts),
            }
        )
    return branches


async def create_branch(workdir: Path, *, name: str, from_commit: str) -> None:
    validate_branch_name(name)
    sha = await _rev_parse(workdir, from_commit)
    try:
        await run_git(
            ["update-ref", "--no-deref", f"refs/heads/{name}", sha], cwd=workdir
        )
    except GitError as exc:
        raise Conflict(f"No se pudo crear la rama '{name}'") from exc


async def delete_branch(workdir: Path, *, name: str, default_branch: str) -> None:
    if name == default_branch:
        # list_branches ya la anuncia como "protected": true -- sin este
        # guard, nada lo impedía de verdad. Borrar la rama por defecto deja
        # el HEAD simbólico del bare repo (symbolic-ref HEAD
        # refs/heads/{default_branch}, fijado una sola vez en
        # git_ops.init_bare) apuntando a un ref que ya no existe: "HEAD sin
        # nacer" para cualquier clone posterior, el mismo problema ya
        # documentado en git/README.md para repos vacíos, pero ahora en un
        # repo que sí tenía historia.
        raise Conflict(
            f"'{name}' es la rama por defecto del repositorio; no se puede borrar"
        )
    try:
        await run_git(["update-ref", "-d", f"refs/heads/{name}"], cwd=workdir)
    except GitError as exc:
        raise NotFound(f"La rama '{name}' no existe") from exc


async def list_tags(workdir: Path) -> list[dict[str, Any]]:
    fmt = (
        f"%(refname:short){_SEP}%(objectname){_SEP}%(*objectname){_SEP}"
        f"%(taggername){_SEP}%(taggeremail){_SEP}%(contents:subject){_SEP}"
        f"%(creatordate:unix)"
    )
    output = await run_git(
        ["for-each-ref", "refs/tags", f"--format={fmt}"], cwd=workdir
    )
    tags = []
    for line in output.decode().strip().splitlines():
        if not line:
            continue
        name, obj_sha, deref_sha, tagger, tagger_email, subject, ts = line.split(_SEP)
        tags.append(
            {
                "name": name,
                "target_commit": deref_sha or obj_sha,
                "message": subject,
                "tagger": {"name": tagger, "email": tagger_email.strip("<>")},
                "created_at": int(ts),
            }
        )
    return tags


def validate_tag_name(name: str) -> None:
    if not _TAG_NAME_RE.match(name):
        raise UnprocessableEntity(
            f"'{name}' no sigue semver (^v\\d+\\.\\d+\\.\\d+(-[a-z0-9.]+)?$)",
            details={"pattern": _TAG_NAME_RE.pattern},
        )


async def create_tag(
    workdir: Path,
    *,
    name: str,
    target_commit: str,
    message: str,
    tagger_name: str,
    tagger_email: str,
) -> None:
    sha = await _rev_parse(workdir, target_commit)
    env_prefix = [
        "-c",
        f"user.name={tagger_name or 'freya'}",
        "-c",
        f"user.email={tagger_email or 'freya@local'}",
    ]
    try:
        await run_git(
            [*env_prefix, "tag", "-a", name, sha, "-m", message], cwd=workdir
        )
    except GitError as exc:
        raise Conflict(f"La tag '{name}' ya existe") from exc


async def delete_tag(workdir: Path, *, name: str) -> None:
    try:
        await run_git(["tag", "-d", name], cwd=workdir)
    except GitError as exc:
        raise NotFound(f"La tag '{name}' no existe") from exc


_LOG_SEP = "\x1e"
# El separador de registro va DELANTE de cada commit, no detrás: así, al
# partir la salida por _LOG_SEP, cada trozo queda "cabecera\n<numstat>",
# cabecera y sus líneas de --numstat juntas y en orden.
_LOG_FMT = f"{_LOG_SEP}%H{_SEP}%h{_SEP}%an{_SEP}%ae{_SEP}%at{_SEP}%s"


async def list_commits(
    workdir: Path,
    *,
    branch: str,
    limit: int,
    offset: int,
    author: str | None,
    since: str | None,
    until: str | None,
) -> list[dict[str, Any]]:
    args = [
        "log",
        f"--format={_LOG_FMT}",
        "--numstat",
        f"--skip={offset}",
        f"-n{limit}",
    ]
    if author:
        args.append(f"--author={author}")
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    args.append(branch)

    try:
        output = await run_git(args, cwd=workdir)
    except GitError as exc:
        raise NotFound(f"'{branch}' no existe en el repositorio") from exc

    commits = []
    for entry in output.decode().split(_LOG_SEP):
        entry = entry.strip("\n")
        if not entry:
            continue
        header, _, stat_block = entry.partition("\n")
        full_hash, short_hash, author_name, author_email, ts, subject = header.split(
            _SEP
        )
        additions = deletions = files_changed = 0
        for stat_line in stat_block.strip().splitlines():
            parts = stat_line.split("\t")
            if len(parts) != 3:
                continue
            add, dele, _path = parts
            additions += int(add) if add.isdigit() else 0
            deletions += int(dele) if dele.isdigit() else 0
            files_changed += 1
        commits.append(
            {
                "hash": full_hash,
                "short_hash": short_hash,
                "message": subject,
                "author": {"name": author_name, "email": author_email},
                "timestamp": int(ts),
                "branch": branch,
                "storage_location": "local",
                "stats": {
                    "additions": additions,
                    "deletions": deletions,
                    "files_changed": files_changed,
                },
            }
        )
    return commits


async def diff(
    workdir: Path, *, base: str, head: str, path: str | None
) -> dict[str, Any]:
    base_sha = await _rev_parse(workdir, base)
    head_sha = await _rev_parse(workdir, head)

    count_out = await run_git(
        ["rev-list", "--count", f"{base_sha}..{head_sha}"], cwd=workdir
    )
    commits_ahead = int(count_out.decode().strip() or 0)

    diff_args = ["diff", "--unified=3", f"{base_sha}..{head_sha}"]
    if path:
        diff_args += ["--", path]
    patch = (await run_git(diff_args, cwd=workdir)).decode("utf-8", errors="replace")

    numstat_args = ["diff", "--numstat", f"{base_sha}..{head_sha}"]
    if path:
        numstat_args += ["--", path]
    numstat = (await run_git(numstat_args, cwd=workdir)).decode()

    files = []
    total_add = total_del = 0
    for line in numstat.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add, dele, file_path = parts
        add_n = int(add) if add.isdigit() else 0
        del_n = int(dele) if dele.isdigit() else 0
        total_add += add_n
        total_del += del_n
        files.append(
            {
                "path": file_path,
                "status": "modified",
                "additions": add_n,
                "deletions": del_n,
            }
        )

    return {
        "base": base,
        "head": head,
        "commits_ahead": commits_ahead,
        "stats": {
            "additions": total_add,
            "deletions": total_del,
            "files_changed": len(files),
        },
        "files": files,
        "patch": patch,
    }


async def tree(workdir: Path, *, ref: str, path: str) -> list[dict[str, Any]]:
    sha = await _rev_parse(workdir, ref)
    target = f"{sha}:{path}" if path else sha
    try:
        output = await run_git(
            ["ls-tree", "--long", target], cwd=workdir
        )
    except GitError as exc:
        raise NotFound(f"'{path or '/'}' no existe en '{ref}'") from exc

    entries = []
    for line in output.decode().strip().splitlines():
        if not line:
            continue
        meta, name = line.split("\t", 1)
        mode, kind, sha_entry, size = meta.split()
        entries.append(
            {
                "name": name,
                "type": "dir" if kind == "tree" else "file",
                "sha": sha_entry,
                "size": None if size == "-" else int(size),
                "mode": mode,
            }
        )
    return entries
