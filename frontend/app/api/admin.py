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
GitClient = Annotated[ServiceClient, Depends(client_dep("git"))]
CicdClient = Annotated[ServiceClient, Depends(client_dep("cicd"))]
ProjectManagerClient = Annotated[ServiceClient, Depends(client_dep("project-manager"))]
GestorDbClient = Annotated[ServiceClient, Depends(client_dep("gestor-db"))]


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
    body: TenantCreate,
    auth_client: AuthClient,
    storage_client: StorageClient,
    git_client: GitClient,
    cicd_client: CicdClient,
    pm_client: ProjectManagerClient,
    gestor_db_client: GestorDbClient,
) -> dict:
    """Crea el tenant y aprovisiona el schema de cada servicio que lo usa
    por proyecto (storage, git, cicd, project-manager, gestor-db) en el
    mismo paso (pedido explícito del usuario: automatizar la creación de un
    tenant, sólo aislamiento de datos -- sin desplegar ningún servicio
    nuevo).

    gestor-db se aprovisiona explícitamente aquí, no por efecto colateral:
    storage/git/cicd/project-manager ya crean el schema al aplicar sus
    propias migraciones (CREATE SCHEMA IF NOT EXISTS), pero depender de eso
    dejaría el schema sin crear si algún día alguno de esos cuatro pasos
    se vuelve opcional. /admin/tenants/{id}/provision de gestor-db es
    idempotente (nunca 409), así que llamarlo aquí también es seguro
    incluso si el schema ya existe por los otros cuatro."""
    tenant = ServiceClient.data(
        await auth_client.post("/admin/tenants", json=body.model_dump())
    )
    await storage_client.post(f"/storage/admin/tenants/{body.id}/provision")
    await git_client.post(f"/git/admin/tenants/{body.id}/provision")
    await cicd_client.post(f"/admin/tenants/{body.id}/provision")
    await pm_client.post(f"/admin/tenants/{body.id}/provision")
    await gestor_db_client.post(f"/admin/tenants/{body.id}/provision")
    return tenant


@router.delete("/tenants/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: str, auth_client: AuthClient, storage_client: StorageClient
) -> None:
    """Elimina el tenant: auth se lleva TODOS los schemas de gestor-db del
    tenant (el que comparten storage/git/cicd/project-manager más cualquier
    schema con nombre adicional que el propio tenant se haya creado vía
    gestor-db "como un RDS") más el registro y los grants; storage limpia
    aparte los bytes en disco (buckets propios y los internos "git",
    "artifacts", "logs" que usan git/cicd por debajo), que viven fuera de
    Postgres. Pedido explícito del usuario: "el admin puede eliminar tenant
    cargándose todo lo que tiene ese tenant" -- el aviso de antemano lo
    muestra el panel antes de llamar aquí."""
    await auth_client.delete(f"/admin/tenants/{tenant_id}")
    await storage_client.delete(f"/storage/admin/tenants/{tenant_id}")


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
