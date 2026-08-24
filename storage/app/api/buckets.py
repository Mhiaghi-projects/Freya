"""Buckets (docs/freya-api-contract.md §5.9)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import Forbidden, current_tenant, require_service_access

from app.deps import ClaimsDep
from app.domain.buckets import (
    bucket_usage,
    create_bucket,
    delete_bucket,
    list_buckets,
)
from app.models.requests import BucketCreate

router = APIRouter(tags=["buckets"])

# El propio storage lo crea al arrancar (ver app/main.py) -- nadie debería
# poder borrarlo por esta API y llevarse el espacio personal de todos los
# usuarios de un tirón.
_PROTECTED_BUCKETS = {"users"}


@router.get("/storage/buckets")
async def list_all(claims: ClaimsDep, request: Request) -> list[dict]:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:storage")
    return await list_buckets(request.app.state.gestor_db, tenant)


@router.put("/storage/buckets/{bucket}", status_code=201)
async def create(
    bucket: str, body: BucketCreate, claims: ClaimsDep, request: Request
) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:storage")
    settings = request.app.state.settings
    return await create_bucket(
        request.app.state.gestor_db,
        tenant,
        bucket=bucket,
        versioning=body.versioning,
        encryption=body.encryption,
        max_versions=body.max_versions,
        quota_bytes=body.quota_bytes or settings.default_quota_bytes,
    )


@router.delete("/storage/buckets/{bucket}", status_code=204)
async def remove(
    bucket: str,
    claims: ClaimsDep,
    request: Request,
    force: bool = Query(default=False),
) -> None:
    tenant = current_tenant()
    require_service_access(claims, tenant, "write:storage")
    if bucket in _PROTECTED_BUCKETS:
        raise Forbidden(f"'{bucket}' es un bucket reservado de la plataforma")
    await delete_bucket(
        request.app.state.gestor_db,
        tenant,
        request.app.state.settings.data_dir,
        bucket=bucket,
        force=force,
    )


@router.get("/storage/buckets/{bucket}/usage")
async def usage(bucket: str, claims: ClaimsDep, request: Request) -> dict:
    tenant = current_tenant()
    require_service_access(claims, tenant, "read:storage")
    return await bucket_usage(request.app.state.gestor_db, tenant, bucket=bucket)
