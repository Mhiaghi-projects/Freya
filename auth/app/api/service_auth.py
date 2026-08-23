"""POST /authenticate/service — JWT de servicio (docs/freya-api-contract.md §15.2).

No expuesto por el gateway: sólo lo llaman los servicios de la malla entre
sí, con sus propias credenciales (service + api_secret), nunca un cliente
externo.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant

from app.domain.accounts import authenticate_service_account
from app.domain.tokens import issue_service_token
from app.models.requests import ServiceAuthRequest

router = APIRouter(tags=["service-auth"])


@router.post("/authenticate/service")
async def authenticate_service(body: ServiceAuthRequest, request: Request) -> dict:
    settings = request.app.state.settings
    keyring = request.app.state.keyring
    gestor_db = request.app.state.gestor_db

    tenant = current_tenant()
    request.app.state.token_rate_limiter.check(f"{tenant}:{body.service}")

    principal = await authenticate_service_account(
        gestor_db, tenant, service=body.service, api_secret=body.api_secret
    )
    access_token, ttl = issue_service_token(
        keyring,
        service=body.service,
        permissions=principal["permissions"],
        issuer=settings.auth_url,
        ttl_seconds=settings.access_token_service_ttl_seconds,
    )
    return {"access_token": access_token, "token_type": "Bearer", "expires_in": ttl}
