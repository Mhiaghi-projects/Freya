"""Configuración de secrets."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "secrets"
    service_version: str = "0.1.0"
    port: int = 8003

    # Master key de envelope encryption (sec-02). Nunca en la base — sólo
    # este fichero montado. Ver docs/ROADMAP.md Fase 3.
    master_key_file: Path = Path("/run/secrets/master_key")

    @property
    def master_key_hex(self) -> str:
        return self.read_secret_file(self.master_key_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
