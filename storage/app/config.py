"""Configuración de storage."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "storage"
    service_version: str = "0.1.0"
    port: int = 8004

    # Los bytes viven en un volumen, no en la base — gestor-db sólo guarda
    # metadatos (docs/ROADMAP.md Fase 4).
    data_dir: Path = Path("/data")

    # Tope duro por subida: con 256 MB de memoria por contenedor, cargar el
    # cuerpo entero en memoria (no hay streaming todavía) exige un límite
    # bajo. Multipart upload (§5.8) queda pendiente precisamente para esto.
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MiB

    default_quota_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB
    default_max_versions: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
