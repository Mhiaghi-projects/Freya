"""GET /.well-known/jwks.json — público, sin autenticación.

No expuesto por el gateway (docs/freya-api-contract.md §15): sólo lo leen
los demás servicios de la malla para validar JWT localmente.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json")
async def jwks(request: Request) -> dict:
    return request.app.state.keyring.jwks()
