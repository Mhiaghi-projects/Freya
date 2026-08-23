"""Autenticación de usuarios (docs/freya-api-contract.md §2). Rutas bajo
/api/v1/auth — así el futuro gateway (Fase 9) las reenvía tal cual."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from freya_common import current_tenant, gdb_mutate

from app.deps import UserDep
from app.domain.refresh import issue_refresh_token, rotate_refresh_token
from app.domain.tokens import issue_user_token
from app.domain.users import (
    authenticate_user,
    change_password,
    create_user,
    get_user,
    role_and_permissions_of,
)
from app.models.requests import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    SignInRequest,
    SignOutRequest,
    SignUpRequest,
)

router = APIRouter(tags=["auth"])


@router.post("/sign-up", status_code=201)
async def sign_up(body: SignUpRequest, request: Request) -> dict:
    gestor_db = request.app.state.gestor_db
    tenant = current_tenant()
    # Mismo limitador que /sign-in (password_rate_limiter), clave distinta
    # ("signup:" de prefijo) para que agotar el cupo de alta de cuentas no
    # bloquee de paso los intentos de login legítimos de ese email, ni al
    # revés -- sin throttling aquí, nada frenaba la creación masiva
    # automatizada de cuentas.
    request.app.state.password_rate_limiter.check(f"signup:{tenant}:{body.email}")
    return await create_user(
        gestor_db,
        tenant,
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
    )


@router.post("/sign-in")
async def sign_in(body: SignInRequest, request: Request) -> dict:
    settings = request.app.state.settings
    keyring = request.app.state.keyring
    gestor_db = request.app.state.gestor_db
    tenant = current_tenant()

    request.app.state.password_rate_limiter.check(f"{tenant}:{body.email}")

    principal = await authenticate_user(
        gestor_db, tenant, email=body.email, password=body.password
    )
    access_token, ttl = issue_user_token(
        keyring,
        user_id=principal["id"],
        tenant_id=tenant,
        role=principal["role"],
        permissions=principal["permissions"],
        issuer=settings.auth_url,
        ttl_seconds=settings.access_token_user_ttl_seconds,
    )
    refresh_token = await issue_refresh_token(
        gestor_db,
        tenant,
        user_id=principal["id"],
        ttl_days=settings.refresh_token_ttl_days,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ttl,
        "must_change_password": principal["must_change_password"],
        "user": {
            "user_id": principal["id"],
            "email": body.email,
            "role": principal["role"],
            "permissions": principal["permissions"],
            "tenant_id": tenant,
        },
    }


@router.post("/refresh-token")
async def refresh_token_endpoint(body: RefreshTokenRequest, request: Request) -> dict:
    settings = request.app.state.settings
    keyring = request.app.state.keyring
    gestor_db = request.app.state.gestor_db
    tenant = current_tenant()

    new_refresh, user_id = await rotate_refresh_token(
        gestor_db, tenant, body.refresh_token, ttl_days=settings.refresh_token_ttl_days
    )
    role, permissions = await role_and_permissions_of(gestor_db, tenant, user_id)
    access_token, ttl = issue_user_token(
        keyring,
        user_id=user_id,
        tenant_id=tenant,
        role=role,
        permissions=permissions,
        issuer=settings.auth_url,
        ttl_seconds=settings.access_token_user_ttl_seconds,
    )
    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "Bearer",
        "expires_in": ttl,
    }


@router.post("/sign-out", status_code=204)
async def sign_out(body: SignOutRequest, request: Request) -> None:
    # Revoca el refresh token presentado; sin él, el access token en curso
    # sigue vivo hasta que caduque solo (15 min) -- revocación de access
    # token con propagación <60s queda pendiente (auth-07).
    gestor_db = request.app.state.gestor_db
    tenant = current_tenant()
    token_id = body.refresh_token.partition(".")[0]
    if token_id:
        await gdb_mutate(
            gestor_db,
            tenant,
            table="refresh_tokens",
            action="update",
            where={"id": token_id},
            data={"revoked_at": datetime.now(UTC).isoformat()},
        )


@router.get("/me")
async def me(claims: UserDep, request: Request) -> dict:
    gestor_db = request.app.state.gestor_db
    tenant = current_tenant()
    return await get_user(gestor_db, tenant, claims["sub"])


@router.post("/change-password", status_code=204)
async def change_password_endpoint(
    body: ChangePasswordRequest, claims: UserDep, request: Request
) -> None:
    gestor_db = request.app.state.gestor_db
    tenant = current_tenant()
    await change_password(
        gestor_db,
        tenant,
        user_id=claims["sub"],
        current_password=body.current_password,
        new_password=body.new_password,
    )
