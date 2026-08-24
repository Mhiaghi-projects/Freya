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

    # blob_store.write ya escribe en streaming, por chunks de 1 MiB, nunca
    # carga el cuerpo entero en memoria -- el límite de 50 MiB de antes
    # databa de cuando eso no era cierto (comentario desde entonces
    # obsoleto). El tope real hoy es la cuota del bucket
    # (default_quota_bytes), no la memoria del contenedor -- este límite
    # por archivo sólo evita que un solo archivo agote la cuota entera de
    # golpe (pedido explícito del usuario: "debe dejarme subir archivos
    # pesados").
    max_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GiB

    default_quota_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GiB
    default_max_versions: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
