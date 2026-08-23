"""Configuración base compartida. Cada servicio la extiende.

Todo viene del entorno con prefijo FREYA_. Los secretos se leen de ficheros
montados en /run/secrets/ durante el bootstrap; una vez `secrets` esté vivo,
`secrets_client` los sustituye.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FREYA_", env_file=".env", extra="ignore"
    )

    # Identidad del servicio
    service_name: str = "unnamed"
    service_version: str = "0.1.0"
    environment: str = "dev"

    # Servidor
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Malla de servicios
    auth_url: str = "https://auth:8002"
    gestor_db_url: str = "https://gestor-db:8001"
    secrets_url: str = "https://secrets:8003"
    storage_url: str = "https://storage:8004"

    # TLS interno
    tls_cert_file: Path = Path("/run/certs/tls.crt")
    tls_key_file: Path = Path("/run/certs/tls.key")
    ca_bundle_file: Path = Path("/run/certs/ca.crt")

    # Autenticación de servicio (docs/freya-api-contract.md §1.1, §15):
    # api_key identifica al servicio, api_secret es el secreto que lo prueba.
    auth_enabled: bool = True
    api_key: str = ""
    api_secret_file: Path = Path("/run/secrets/api_secret")
    jwks_cache_seconds: int = 600

    # Tenant por defecto para el uso interno de la plataforma
    default_tenant: str = "freya"

    def read_secret_file(self, path: Path) -> str:
        """Lee un secreto de fichero montado. Vacío si no existe."""
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""

    @property
    def api_secret(self) -> str:
        return self.read_secret_file(self.api_secret_file)
