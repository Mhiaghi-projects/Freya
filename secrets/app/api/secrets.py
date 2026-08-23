"""Vault de secretos (docs/freya-api-contract.md §9).

Un tenant sólo accede a su propio namespace: el {namespace} de la ruta tiene
que coincidir con X-Tenant-Context, si no es TENANT_MISMATCH — igual que
gestor-db exige que el "schema" del cuerpo pertenezca al tenant autenticado.

La `key` es `{key:path}`, no `{key}`: los secretos de arranque importados
usan namespacing jerárquico (`bootstrap/storage/api_secret`, ver
infra/scripts/import_bootstrap_secrets.py), igual que storage con sus
objetos (`app/api/objects.py` en storage). Orden de las rutas: FastAPI
resuelve por orden de registro cuando dos patrones podrían encajar con la
misma petición, y `{key:path}` es voraz -- consume el resto de la URL
incluidas barras. "/audit-logs" y "/{key:path}/versions" tienen que
registrarse ANTES que "/{key:path}" a secas — si no, la ruta genérica los
captura primero (cualquier cosa con barras encaja como key) y esas rutas
más específicas nunca llegan a su handler real.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from freya_common import TenantMismatch, current_tenant, require_permissions

from app.deps import ClaimsDep
from app.domain.vault import (
    create_secret,
    delete_secret,
    get_secret,
    list_audit_logs,
    list_secrets,
    list_versions,
    record_audit,
    rotate_secret,
)
from app.models.requests import SecretCreate, SecretRotate, SecretUpdate

router = APIRouter(tags=["secrets"])


def _check_namespace(namespace: str) -> str:
    tenant = current_tenant()
    if namespace != tenant:
        raise TenantMismatch(
            f"El namespace '{namespace}' no pertenece al tenant autenticado",
            details={"namespace": namespace, "tenant": tenant},
        )
    return tenant


def _actor(claims: dict) -> str:
    return str(claims.get("service") or claims.get("sub") or "")


@router.post("/secrets/{namespace}", status_code=201)
async def create(
    namespace: str, body: SecretCreate, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:secrets")
    tenant = _check_namespace(namespace)
    result = await create_secret(
        request.app.state.gestor_db,
        tenant,
        request.app.state.master_key,
        request.app.state.storage,
        key=body.key,
        value=body.value,
        type_=body.type,
        description=body.description,
        expires_at=body.expires_at,
        overwrite=body.overwrite,
    )
    await record_audit(
        request.app.state.gestor_db,
        tenant,
        key=body.key,
        action="create",
        actor_service=_actor(claims),
    )
    result.pop("value", None)
    return result


@router.get("/secrets/{namespace}")
async def list_all(namespace: str, claims: ClaimsDep, request: Request) -> list[dict]:
    require_permissions(claims, "read:secrets")
    tenant = _check_namespace(namespace)
    return await list_secrets(request.app.state.gestor_db, tenant)


@router.get("/secrets/{namespace}/audit-logs")
async def audit_logs(
    namespace: str,
    claims: ClaimsDep,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
) -> list[dict]:
    require_permissions(claims, "read:secrets")
    tenant = _check_namespace(namespace)
    return await list_audit_logs(
        request.app.state.gestor_db, tenant, limit=limit, action_filter=action
    )


@router.get("/secrets/{namespace}/{key:path}/versions")
async def versions(
    namespace: str, key: str, claims: ClaimsDep, request: Request
) -> list[dict]:
    require_permissions(claims, "read:secrets")
    tenant = _check_namespace(namespace)
    return await list_versions(request.app.state.gestor_db, tenant, key=key)


@router.get("/secrets/{namespace}/{key:path}")
async def read_secret(
    namespace: str,
    key: str,
    claims: ClaimsDep,
    request: Request,
    version: int | None = Query(default=None),
    metadata_only: bool = Query(default=False),
) -> dict:
    require_permissions(claims, "read:secrets")
    tenant = _check_namespace(namespace)
    result = await get_secret(
        request.app.state.gestor_db,
        tenant,
        request.app.state.master_key,
        request.app.state.storage,
        key=key,
        version=version,
        metadata_only=metadata_only,
    )
    await record_audit(
        request.app.state.gestor_db,
        tenant,
        key=key,
        action="read",
        actor_service=_actor(claims),
    )
    return result


@router.put("/secrets/{namespace}/{key:path}")
async def update(
    namespace: str, key: str, body: SecretUpdate, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:secrets")
    tenant = _check_namespace(namespace)
    result = await create_secret(
        request.app.state.gestor_db,
        tenant,
        request.app.state.master_key,
        request.app.state.storage,
        key=key,
        value=body.value,
        type_="generic",
        description="",
        expires_at=body.expires_at,
        overwrite=True,
    )
    await record_audit(
        request.app.state.gestor_db,
        tenant,
        key=key,
        action="update",
        actor_service=_actor(claims),
    )
    result.pop("value", None)
    return result


@router.delete("/secrets/{namespace}/{key:path}", status_code=204)
async def delete(
    namespace: str,
    key: str,
    claims: ClaimsDep,
    request: Request,
    version: int | None = Query(default=None),
) -> None:
    require_permissions(claims, "write:secrets")
    tenant = _check_namespace(namespace)
    await delete_secret(
        request.app.state.gestor_db,
        tenant,
        request.app.state.storage,
        key=key,
        version=version,
    )
    await record_audit(
        request.app.state.gestor_db,
        tenant,
        key=key,
        action="delete",
        actor_service=_actor(claims),
    )


@router.post("/secrets/{namespace}/{key:path}/rotate")
async def rotate(
    namespace: str, key: str, body: SecretRotate, claims: ClaimsDep, request: Request
) -> dict:
    require_permissions(claims, "write:secrets")
    tenant = _check_namespace(namespace)
    result = await rotate_secret(
        request.app.state.gestor_db,
        tenant,
        request.app.state.master_key,
        request.app.state.storage,
        key=key,
        new_value=body.new_value,
    )
    await record_audit(
        request.app.state.gestor_db,
        tenant,
        key=key,
        action="rotate",
        actor_service=_actor(claims),
    )
    return result
