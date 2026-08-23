"""Configuración de __SERVICE_NAME__."""

from __future__ import annotations

from functools import lru_cache

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "__SERVICE_NAME__"
    service_version: str = "0.1.0"
    port: int = __SERVICE_PORT__

    # Ajustes propios del servicio van aquí.
    # ejemplo_timeout_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
