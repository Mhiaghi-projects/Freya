"""Configuración de git."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "git"
    service_version: str = "0.1.0"
    port: int = 8005

    # Espacio de trabajo efímero donde se materializan los repos bare para
    # operar con el binario real de git. No es la fuente de verdad — eso es
    # storage (bucket "git", ver app/domain/repo_store.py) — así que puede
    # perderse sin pérdida de datos; se reconstruye en la próxima operación.
    scratch_dir: Path = Path("/scratch")

    # Nombre fijo del bucket de storage donde vive cada tenant. Cada repo es
    # un puñado de objetos (pack + refs.json), no uno por objeto git suelto:
    # storage no está pensado para miles de objetos diminutos por bucket.
    git_bucket: str = "git"

    git_binary: str = "git"

    # Disparador de push -> pipeline (ROADMAP.md ci-04, git-08): git no
    # dispara nada por sí mismo hasta que un push termina de persistirse,
    # así que sólo necesita saber a quién avisar.
    cicd_url: str = "https://cicd:8007"


@lru_cache
def get_settings() -> Settings:
    return Settings()
