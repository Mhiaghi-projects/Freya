"""Configuración de gestor-db."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "gestor-db"
    service_version: str = "0.1.0"
    port: int = 8001

    # Conexión nativa a database, por la red privada freya-db. Único
    # servicio de Freya con permiso para hablar el protocolo PostgreSQL.
    # Sin "postgres_db" fijo: cada tenant es su propia base (resolve_database
    # decide cuál en cada petición), y las operaciones de catálogo usan
    # siempre la base ancla "postgres" (app.domain.pool.ANCHOR_DATABASE).
    postgres_host: str = "freya-database"
    postgres_port: int = 5432
    postgres_user: str = "freya"
    postgres_password_file: Path = Path("/run/secrets/postgres_password")

    # Sin pool persistente (una base física por tenant, conexión por
    # petición) -- este timeout pasa directo a asyncpg.connect().
    pool_command_timeout_seconds: float = 30.0

    # Modo bootstrap (gdb-03): token estático hasta que auth exista.
    bootstrap_token_file: Path = Path("/run/secrets/bootstrap_token")

    # Límite de tiempo por consulta (gdb-04). El límite de filas lo fija
    # cada petición (limit/offset, tope 200 — ver models/requests.py).
    query_timeout_seconds: float = 15.0

    @property
    def postgres_password(self) -> str:
        return self.read_secret_file(self.postgres_password_file)

    @property
    def bootstrap_token(self) -> str:
        return self.read_secret_file(self.bootstrap_token_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
