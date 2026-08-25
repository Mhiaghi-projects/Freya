"""Configuración de frontend."""

from __future__ import annotations

from functools import lru_cache

from freya_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "frontend"
    service_version: str = "0.1.0"
    port: int = 8000

    # Backends que el gateway conoce (docs/ROADMAP.md Fase 9). auth_url y
    # storage_url ya vienen de BaseServiceSettings.
    git_url: str = "https://freya-git:8005"
    project_manager_url: str = "https://freya-project-manager:8006"
    cicd_url: str = "https://freya-cicd:8007"
    gestor_monitoring_url: str = "https://freya-gestor-monitoring:8008"
    gamification_url: str = "https://freya-gamification:8009"
    # gestor-db "como un RDS" para proyectos propios (docs/DECISIONS.md) --
    # nunca expone /migrations ni DROP DATABASE, sólo query/mutate/tables/
    # databases (list+create), ver app/api/database.py.
    gestor_db_url: str = "https://freya-gestor-db:8001"

    # Cookies de sesión: el navegador nunca ve el JWT -- sólo frontend, que
    # lo reenvía como Authorization al hacer de gateway (app/infra/gateway.py).
    access_cookie_name: str = "freya_access"
    refresh_cookie_name: str = "freya_refresh"
    # Igual al TTL real del refresh token de auth (config.py de auth,
    # refresh_token_ttl_days) -- si difieren, la cookie sólo puede caducar
    # antes que el token, nunca despues (fallo seguro).
    refresh_cookie_days: int = 30

    # Rate limiting por tenant (docs/ROADMAP.md Fase 11), ver
    # app/infra/rate_limit.py.
    tenant_rate_limit_max_attempts: int = 300
    tenant_rate_limit_window_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
