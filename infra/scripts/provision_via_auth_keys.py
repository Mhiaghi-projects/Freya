#!/usr/bin/env python3
"""Da de alta una cuenta de servicio llamando directamente a
app.domain.accounts.create_service_account con las credenciales que auth
usa para hablar consigo mismo (SelfTokenProvider) -- nunca pasa por
POST /admin/service-accounts.

Por qué: ese endpoint exige auth_enabled=false (modo bootstrap) o un JWT de
usuario admin. Lo primero ya no es una puerta reutilizable -- gestor-db
invalidó su token de bootstrap para siempre al cerrar la Fase 2 (ver
docs/ROADMAP.md, "el token de bootstrap queda inválido"): poner
FREYA_AUTH_ENABLED=false en auth hace que auth intente hablar con gestor-db
usando ESE token muerto para CUALQUIER llamada, no sólo /admin/* -- se
descubrió en vivo tratando de aprovisionar 'freya-ops' (infra\\backups ->
storage), que dejaba a auth entero sin poder escribir en gestor-db durante
la ventana. Lo segundo (JWT admin) no existe todavía como cuenta
persistente.

Este script evita el problema por completo: corre DENTRO del contenedor de
auth (tiene su keyring y su código), firma su propio JWT de servicio
exactamente como hace SelfTokenProvider en producción, y llama al dominio
en proceso -- cero saltos HTTP de más, cero modo bootstrap.

Uso (nunca a mano, sólo desde New-FreyaServiceAccount):
    docker exec -i freya-auth python3 - <<< "$(cat este_fichero)"
con SERVICE_NAME, API_SECRET, PERMISSIONS_CSV como variables de entorno.
"""

from __future__ import annotations

import asyncio
import os

from app.config import get_settings
from app.domain.accounts import create_service_account, update_service_account_permissions
from app.domain.keys import KeyRing
from app.infra.gestor_db_client import SelfTokenProvider, build_gestor_db_client
from freya_common import build_http_client


async def main() -> None:
    service = os.environ["SERVICE_NAME"]
    api_secret = os.environ["API_SECRET"]
    permissions = [p for p in os.environ.get("PERMISSIONS_CSV", "").split(",") if p]

    settings = get_settings()
    keyring = KeyRing.load(settings.signing_keys_dir)
    ca = str(settings.ca_bundle_file) if settings.ca_bundle_file.exists() else None
    http = build_http_client(ca)
    tokens = SelfTokenProvider(
        keyring,
        service=settings.service_name,
        permissions=settings.gestor_db_client_permissions,
        issuer=settings.auth_url,
        ttl_seconds=settings.access_token_service_ttl_seconds,
    )
    client = build_gestor_db_client(
        settings.gestor_db_url, settings.service_name, http, tokens
    )

    try:
        try:
            account_id = await create_service_account(
                client,
                settings.default_tenant,
                service=service,
                api_secret=api_secret,
                permissions=permissions,
            )
            print(f"cuenta '{service}' creada: {account_id}")
        except Exception as exc:  # noqa: BLE001 - probablemente ya existe (UNIQUE)
            print(f"creación falló ({exc}), se intenta actualizar permisos")
            await update_service_account_permissions(
                client,
                settings.default_tenant,
                service=service,
                permissions=permissions,
            )
            print(f"cuenta '{service}' ya existía: permisos actualizados a {permissions}")
    finally:
        await http.aclose()


if __name__ == "__main__":
    asyncio.run(main())
