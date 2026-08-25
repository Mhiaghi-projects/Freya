"""Aprovisionamiento de tenants nuevos para git: aplica las propias
migraciones contra el schema del tenant (mismo patrón que
storage/app/api/admin.py) -- el bucket de storage del tenant se crea solo,
bajo demanda, al crear el primer repo (repo_store.ensure_bucket). Sólo
role: admin, no es un acceso por proyecto."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from freya_common import Forbidden, load_migrations

from app.deps import ClaimsDep

router = APIRouter(tags=["admin"])


@router.post("/git/admin/tenants/{tenant}/provision", status_code=201)
async def provision(tenant: str, claims: ClaimsDep, request: Request) -> dict:
    if claims.get("role") != "admin":
        raise Forbidden("Sólo un admin puede aprovisionar un tenant")
    migrations = load_migrations(Path("/srv/migrations"))
    await request.app.state.gestor_db.post(
        "/migrations",
        tenant=tenant,
        json={"database": tenant, "migrations": migrations},
    )
    return {"tenant": tenant}
