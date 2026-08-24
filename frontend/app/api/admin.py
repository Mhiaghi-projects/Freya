"""Gestión de usuarios (docs/freya-api-contract.md §3, disponible en
auth/app/api/admin.py): proxy delgado -- auth exige role: admin por su
cuenta (AdminDep), esta capa no repite el chequeo."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from freya_common import ServiceClient
from pydantic import BaseModel, Field

from app.infra.gateway import client_dep

router = APIRouter(prefix="/api/admin", tags=["admin"])
AuthClient = Annotated[ServiceClient, Depends(client_dep("auth"))]
StorageClient = Annotated[ServiceClient, Depends(client_dep("storage"))]


class UserCreate(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")
    extra_permissions: list[str] = Field(default_factory=list)


class PermissionsUpdate(BaseModel):
    extra_permissions: list[str] = Field(default_factory=list)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


class TenantCreate(BaseModel):
    id: str = Field(min_length=1, max_length=63, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)


class TenantGrantUpdate(BaseModel):
    permissions: list[str] = Field(default_factory=list)


@router.get("/roles")
async def list_roles(client: AuthClient) -> dict:
    return ServiceClient.data(await client.get("/admin/roles"))


@router.get("/service-grants")
async def list_service_grants(client: AuthClient) -> dict:
    return ServiceClient.data(await client.get("/admin/service-grants"))


@router.get("/users")
async def list_users(client: AuthClient) -> list:
    return ServiceClient.data(await client.get("/admin/users"))


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, client: AuthClient) -> dict:
    response = await client.post("/admin/users", json=body.model_dump())
    return ServiceClient.data(response)


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_password(user_id: str, body: PasswordReset, client: AuthClient) -> None:
    await client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": body.new_password},
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, client: AuthClient) -> None:
    await client.delete(f"/admin/users/{user_id}")


@router.patch("/users/{user_id}/permissions")
async def update_permissions(
    user_id: str, body: PermissionsUpdate, client: AuthClient
) -> dict:
    response = await client.request(
        "PATCH",
        f"/admin/users/{user_id}/permissions",
        json={"extra_permissions": body.extra_permissions},
    )
    return ServiceClient.data(response)


@router.get("/tenant-grants")
async def list_tenant_grants(client: AuthClient) -> dict:
    return ServiceClient.data(await client.get("/admin/tenant-grants"))


@router.get("/tenants")
async def list_tenants(client: AuthClient) -> list:
    return ServiceClient.data(await client.get("/admin/tenants"))


@router.post("/tenants", status_code=201)
async def create_tenant(
    body: TenantCreate, auth_client: AuthClient, storage_client: StorageClient
) -> dict:
    """Crea el tenant y aprovisiona su espacio de storage en el mismo paso
    (pedido explícito del usuario: automatizar la creación de un tenant,
    sólo aislamiento de datos -- sin desplegar ningún servicio nuevo)."""
    tenant = ServiceClient.data(
        await auth_client.post("/admin/tenants", json=body.model_dump())
    )
    await storage_client.post(f"/storage/admin/tenants/{body.id}/provision")
    return tenant


@router.get("/users/{user_id}/tenants")
async def get_user_tenant_grants(user_id: str, client: AuthClient) -> dict:
    return ServiceClient.data(await client.get(f"/admin/users/{user_id}/tenants"))


@router.put("/users/{user_id}/tenants/{tenant_id}")
async def update_user_tenant_grant(
    user_id: str, tenant_id: str, body: TenantGrantUpdate, client: AuthClient
) -> dict:
    response = await client.request(
        "PUT",
        f"/admin/users/{user_id}/tenants/{tenant_id}",
        json={"permissions": body.permissions},
    )
    return ServiceClient.data(response)
