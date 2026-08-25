"""POST /admin/service-accounts — alta de cuentas de servicio.

Protegido por AdminDep: token de bootstrap propio mientras
AUTH_ENABLED=false, role: admin después. No es parte de la superficie
externa del contrato (§3 es administración de USUARIOS del tenant); esto es
lo mínimo para provisionar las cuentas de servicio de la propia malla.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from freya_common import current_tenant

from app.deps import AdminDep
from app.domain.accounts import (
    create_service_account,
    update_service_account_permissions,
)
from app.domain.tenants import (
    TENANT_GRANTABLE_PERMISSIONS,
    create_tenant,
    delete_tenant,
    list_tenants,
    set_tenant_grant,
    tenant_grants_of,
)
from app.domain.users import (
    ROLE_PERMISSIONS,
    SERVICE_GRANTS,
    admin_reset_password,
    create_user,
    delete_user,
    list_users,
    update_user_permissions,
)
from app.models.requests import (
    AdminPasswordReset,
    AdminPermissionsUpdate,
    AdminUserCreate,
    ServiceAccountCreate,
    ServiceAccountPermissionsUpdate,
    TenantCreate,
    TenantGrantUpdate,
)

router = APIRouter(tags=["admin"])


@router.post("/admin/service-accounts", status_code=201)
async def create_account(
    body: ServiceAccountCreate, _admin: AdminDep, request: Request
) -> dict:
    account_id = await create_service_account(
        request.app.state.gestor_db,
        current_tenant(),
        service=body.service,
        api_secret=body.api_secret,
        permissions=body.permissions,
    )
    return {"id": account_id, "service": body.service}


@router.patch("/admin/service-accounts/{service}")
async def update_account_permissions(
    service: str,
    body: ServiceAccountPermissionsUpdate,
    _admin: AdminDep,
    request: Request,
) -> dict:
    await update_service_account_permissions(
        request.app.state.gestor_db,
        current_tenant(),
        service=service,
        permissions=body.permissions,
    )
    return {"service": service, "permissions": body.permissions}


@router.get("/admin/roles")
async def list_roles(_admin: AdminDep) -> dict:
    return dict(ROLE_PERMISSIONS)


@router.get("/admin/service-grants")
async def list_service_grants(_admin: AdminDep) -> dict:
    return dict(SERVICE_GRANTS)


@router.get("/admin/users")
async def list_admin_users(_admin: AdminDep, request: Request) -> list:
    return await list_users(request.app.state.gestor_db, current_tenant())


@router.post("/admin/users", status_code=201)
async def create_admin_user(
    body: AdminUserCreate, _admin: AdminDep, request: Request
) -> dict:
    return await create_user(
        request.app.state.gestor_db,
        current_tenant(),
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
        extra_permissions=body.extra_permissions,
    )


@router.patch("/admin/users/{user_id}/permissions")
async def update_admin_user_permissions(
    user_id: str, body: AdminPermissionsUpdate, _admin: AdminDep, request: Request
) -> dict:
    await update_user_permissions(
        request.app.state.gestor_db,
        current_tenant(),
        user_id=user_id,
        extra_permissions=body.extra_permissions,
    )
    return {"user_id": user_id, "extra_permissions": body.extra_permissions}


@router.post("/admin/users/{user_id}/reset-password", status_code=204)
async def reset_user_password(
    user_id: str, body: AdminPasswordReset, _admin: AdminDep, request: Request
) -> None:
    await admin_reset_password(
        request.app.state.gestor_db,
        current_tenant(),
        user_id=user_id,
        new_password=body.new_password,
    )


@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_admin_user(user_id: str, _admin: AdminDep, request: Request) -> None:
    await delete_user(request.app.state.gestor_db, current_tenant(), user_id=user_id)


@router.get("/admin/tenant-grants")
async def list_tenant_grants(_admin: AdminDep) -> dict:
    return dict(TENANT_GRANTABLE_PERMISSIONS)


@router.get("/admin/tenants")
async def list_admin_tenants(_admin: AdminDep, request: Request) -> list:
    return await list_tenants(request.app.state.gestor_db)


@router.post("/admin/tenants", status_code=201)
async def create_admin_tenant(
    body: TenantCreate, admin: AdminDep, request: Request
) -> dict:
    return await create_tenant(
        request.app.state.gestor_db,
        tenant_id=body.id,
        name=body.name,
        created_by=admin.get("sub"),
    )


@router.delete("/admin/tenants/{tenant_id}", status_code=204)
async def delete_admin_tenant(
    tenant_id: str, _admin: AdminDep, request: Request
) -> None:
    await delete_tenant(request.app.state.gestor_db, tenant_id)


@router.get("/admin/users/{user_id}/tenants")
async def get_user_tenant_grants(
    user_id: str, _admin: AdminDep, request: Request
) -> dict:
    return await tenant_grants_of(request.app.state.gestor_db, user_id)


@router.put("/admin/users/{user_id}/tenants/{tenant_id}")
async def update_user_tenant_grant(
    user_id: str,
    tenant_id: str,
    body: TenantGrantUpdate,
    _admin: AdminDep,
    request: Request,
) -> dict:
    await set_tenant_grant(
        request.app.state.gestor_db,
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=body.permissions,
    )
    return {"user_id": user_id, "tenant_id": tenant_id, "permissions": body.permissions}
