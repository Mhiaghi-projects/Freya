"""Configuración de auth."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "auth"
    service_version: str = "0.1.0"
    port: int = 8002

    # Claves de firma RSA (docs/freya-api-contract.md §15.1). Un fichero por
    # clave; la más nueva firma, todas se publican en el JWKS mientras se
    # retiran.
    signing_keys_dir: Path = Path("/run/secrets/signing_keys")

    # Vida de los tokens.
    access_token_service_ttl_seconds: int = 300
    access_token_user_ttl_seconds: int = 900
    refresh_token_ttl_days: int = 30

    # Bootstrap: mientras AUTH_ENABLED=false, auth habla con gestor-db
    # usando su token estático, y sus propios endpoints de administración
    # exigen el suyo — no hay JWT posible hasta que exista al menos una
    # cuenta de servicio.
    gestor_db_bootstrap_token_file: Path = Path("/run/gestor-db-bootstrap-token")
    bootstrap_token_file: Path = Path("/run/secrets/bootstrap_token")

    # Permisos mínimos que auth se autoconcede para hablar con gestor-db
    # (SelfTokenProvider). Nunca "*".
    gestor_db_client_permissions: list[str] = [
        "read:database", "write:database",
    ]

    # Límite de tasa de /token y /auth/sign-in, por (IP, identificador). El
    # login es el único endpoint adivinable por fuerza bruta.
    token_rate_limit_max_attempts: int = 20
    token_rate_limit_window_seconds: float = 60.0
    password_rate_limit_max_attempts: int = 5
    password_rate_limit_window_seconds: float = 60.0

    @property
    def gestor_db_bootstrap_token(self) -> str:
        return self.read_secret_file(self.gestor_db_bootstrap_token_file)

    @property
    def bootstrap_token(self) -> str:
        return self.read_secret_file(self.bootstrap_token_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
