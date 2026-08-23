"""Configuración de gamification."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "gamification"
    service_version: str = "0.1.0"
    port: int = 8009

    project_manager_url: str = "https://freya-project-manager:8006"
    task_sync_interval_seconds: int = 15

    # Sincronización desde GitHub Issues en vez de project-manager
    # (docs/DECISIONS.md, "migrar git/project-manager/cicd a GitHub").
    # Apagado por defecto -- ver app/domain/github_task_sync.py.
    use_github_task_sync: bool = False
    github_owner: str = ""
    github_repos: str = ""  # separados por coma, p.ej. "auth,storage,frontend"
    github_default_user_id: str = ""
    github_pat_file: Path = Path("/run/secrets/github_pat")

    @property
    def github_pat(self) -> str:
        return self.read_secret_file(self.github_pat_file)

    @property
    def github_repo_list(self) -> list[str]:
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
