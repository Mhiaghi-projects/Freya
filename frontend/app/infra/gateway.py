"""Construye un ServiceClient por petición hacia un backend conocido,
reenviando el token de acceso del propio usuario (nunca un token de
servicio): las respuestas que ve el navegador quedan acotadas exactamente
por el role/permissions de quien inició sesión, sin ninguna elevación de
privilegio en frontend."""

from __future__ import annotations

import httpx
from fastapi import Request
from freya_common import ServiceClient

from app.config import Settings
from app.deps import SettingsDep, WebSessionDep


class _StaticToken:
    def __init__(self, token: str) -> None:
        self._token = token

    async def token(self) -> str:
        return self._token


_BACKENDS = {
    "auth": lambda s: s.auth_url,
    "storage": lambda s: s.storage_url,
    "git": lambda s: s.git_url,
    "project-manager": lambda s: s.project_manager_url,
    "cicd": lambda s: s.cicd_url,
    "gestor-monitoring": lambda s: s.gestor_monitoring_url,
    "gamification": lambda s: s.gamification_url,
    "gestor-db": lambda s: s.gestor_db_url,
}


def backend_client(
    name: str, *, settings: Settings, http: httpx.AsyncClient, access_token: str
) -> ServiceClient:
    try:
        base_url = _BACKENDS[name](settings)
    except KeyError:
        raise ValueError(f"backend desconocido: {name}") from None
    return ServiceClient(base_url, "frontend", http, _StaticToken(access_token))


def client_dep(backend: str):
    """Dependencia FastAPI: un ServiceClient hacia `backend`, autenticado
    con el access token de la sesión del navegador. Uso:
    `client: Annotated[ServiceClient, Depends(client_dep("git"))]`."""

    def _dep(
        session: WebSessionDep, request: Request, settings: SettingsDep
    ) -> ServiceClient:
        return backend_client(
            backend,
            settings=settings,
            http=request.app.state.http,
            access_token=session.access_token,
        )

    return _dep
