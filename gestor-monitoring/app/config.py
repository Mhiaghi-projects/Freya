"""Configuración de gestor-monitoring."""

from __future__ import annotations

from functools import lru_cache

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "gestor-monitoring"
    service_version: str = "0.1.0"
    port: int = 8008

    # Backends nativos en freya-mon (docs/ARCHITECTURE.md §4), sin TLS de
    # Freya -- mismo principio que gestor-db hablando Postgres con database.
    metrics_url: str = "http://freya-metrics:8428"
    logs_url: str = "http://freya-logs:9428"

    # Única excepción del proyecto a "nada toca Docker salvo freya.ps1":
    # sólo lectura, sólo para descubrir contenedores por freya.service.
    docker_socket: str = "/var/run/docker.sock"

    scrape_interval_seconds: int = 30
    scrape_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
