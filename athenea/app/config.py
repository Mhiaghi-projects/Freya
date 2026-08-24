"""Configuración de athenea."""

from __future__ import annotations

from functools import lru_cache

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "athenea"
    service_version: str = "0.1.0"
    port: int = 8010

    # Athenea es un tenant externo, no uso interno de la plataforma (ver
    # docs/ARCHITECTURE.md §9) -- su propio schema en gestor-db, separado
    # del de "freya".
    default_tenant: str = "athenea"


@lru_cache
def get_settings() -> Settings:
    return Settings()
