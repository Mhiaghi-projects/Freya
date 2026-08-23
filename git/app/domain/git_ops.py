"""Envoltorio fino sobre el binario real de git (docs/ARCHITECTURE.md §5:
"FastAPI sobre git http-backend"). No reimplementa el protocolo ni el
modelo de objetos — sólo invoca `git` como subproceso y traduce su salida.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import get_settings


class GitError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stderr: bytes) -> None:
        self.args_ = args
        self.returncode = returncode
        self.stderr = stderr.decode("utf-8", errors="replace")
        super().__init__(f"git {' '.join(args)} salió con {returncode}: {self.stderr}")


async def run_git(
    args: list[str], *, cwd: Path | None = None, input_bytes: bytes | None = None
) -> bytes:
    """Ejecuta git y devuelve stdout. Lanza GitError si el proceso falla."""
    proc = await asyncio.create_subprocess_exec(
        get_settings().git_binary,
        *args,
        cwd=str(cwd) if cwd else None,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=input_bytes)
    if proc.returncode != 0:
        raise GitError(args, proc.returncode or -1, stderr)
    return stdout


async def init_bare(workdir: Path, default_branch: str) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    await run_git(["init", "--quiet", "--bare", str(workdir)])
    await run_git(
        ["symbolic-ref", "HEAD", f"refs/heads/{default_branch}"], cwd=workdir
    )


async def index_pack(workdir: Path, pack_bytes: bytes) -> None:
    """Registra un packfile recibido de storage: sin `-o`, git-index-pack
    escribe pack+idx bajo objects/pack/ con el nombre que deriva de su
    propio hash de contenido -- no hace falta (ni conviene) elegirlo aquí."""
    (workdir / "objects" / "pack").mkdir(parents=True, exist_ok=True)
    await run_git(["index-pack", "--stdin"], cwd=workdir, input_bytes=pack_bytes)


async def repack(workdir: Path) -> Path | None:
    """Consolida todos los objetos sueltos y packs en uno solo. Devuelve la
    ruta del pack resultante, o None si el repo no tiene ningún objeto."""
    await run_git(["repack", "-a", "-d", "--quiet"], cwd=workdir)
    packs = sorted((workdir / "objects" / "pack").glob("*.pack"))
    return packs[0] if packs else None


async def for_each_ref(workdir: Path) -> list[tuple[str, str]]:
    """[(refname, sha)], p.ej. [("refs/heads/main", "abc123...")]."""
    output = await run_git(
        ["for-each-ref", "--format=%(refname) %(objectname)"], cwd=workdir
    )
    lines = output.decode("utf-8").strip().splitlines()
    return [tuple(line.split(" ", 1)) for line in lines if line]  # type: ignore[misc]


async def symbolic_ref_head(workdir: Path) -> str:
    output = await run_git(["symbolic-ref", "--quiet", "HEAD"], cwd=workdir)
    return output.decode("utf-8").strip()


async def write_ref(workdir: Path, refname: str, sha: str) -> None:
    await run_git(["update-ref", refname, sha], cwd=workdir)
