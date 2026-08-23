"""Configuración de cicd."""

from __future__ import annotations

from functools import lru_cache

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "cicd"
    service_version: str = "0.1.0"
    port: int = 8007

    # Repositorio de Freya, montado de sólo lectura: es el contexto de
    # build que necesita `docker build` para construir la etapa `dev` de
    # cada servicio (COPY freya-common/, COPY <nombre>/...).
    workspace_dir: str = "/workspace"

    docker_binary: str = "docker"
    build_timeout_seconds: float = 180.0
    run_timeout_seconds: float = 120.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
