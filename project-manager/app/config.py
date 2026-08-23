"""Configuración de project-manager."""

from __future__ import annotations

from functools import lru_cache

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "project-manager"
    service_version: str = "0.1.0"
    port: int = 8006


@lru_cache
def get_settings() -> Settings:
    return Settings()
