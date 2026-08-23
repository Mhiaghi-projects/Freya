"""Traduce la sesión de auth (JWT + refresh token) a cookies httponly: el
navegador nunca ve ningún token, sólo estas rutas y app/deps.py lo hacen."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request, Response
from freya_common import FreyaError, ServiceClient, Unauthorized
from pydantic import BaseModel, Field

from app.deps import (
    SettingsDep,
    WebSessionDep,
    clear_session_cookies,
    set_session_cookies,
)
from app.infra.gateway import backend_client

router = APIRouter(prefix="/api/session", tags=["session"])


class SignInBody(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


@router.post("/sign-in")
async def sign_in(
    body: SignInBody, request: Request, response: Response, settings: SettingsDep
) -> dict:
    auth = ServiceClient(settings.auth_url, "frontend", request.app.state.http)
    try:
        result = await auth.post(
            "/api/v1/auth/sign-in",
            json={"email": body.email, "password": body.password},
        )
    except FreyaError as exc:
        # Sólo un 401 de verdad de auth significa "credenciales
        # inválidas". Cualquier otra cosa (auth caído, 503, timeout) es un
        # problema de infraestructura -- decirle al usuario que su
        # contraseña está mal cuando en realidad auth no responde es
        # engañoso y le manda a intentar un reset que no arregla nada.
        if exc.status_code == 401:
            raise Unauthorized("email o contraseña inválidos") from exc
        raise

    data = ServiceClient.data(result)
    set_session_cookies(
        response,
        settings,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
    )
    return {
        "user": data["user"],
        "must_change_password": data["must_change_password"],
    }


@router.post("/sign-out", status_code=204)
async def sign_out(request: Request, response: Response, settings: SettingsDep) -> None:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    clear_session_cookies(response, settings)
    if not refresh_token:
        return
    auth = ServiceClient(settings.auth_url, "frontend", request.app.state.http)
    with contextlib.suppress(FreyaError):
        await auth.post("/api/v1/auth/sign-out", json={"refresh_token": refresh_token})


@router.get("/me")
async def me(session: WebSessionDep, request: Request, settings: SettingsDep) -> dict:
    client = backend_client(
        "auth",
        settings=settings,
        http=request.app.state.http,
        access_token=session.access_token,
    )
    profile = ServiceClient.data(await client.get("/api/v1/auth/me"))
    return {
        **profile,
        "user_id": profile["id"],
        "permissions": session.claims.get("permissions", []),
    }


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordBody,
    session: WebSessionDep,
    request: Request,
    settings: SettingsDep,
) -> None:
    client = backend_client(
        "auth",
        settings=settings,
        http=request.app.state.http,
        access_token=session.access_token,
    )
    await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": body.current_password,
            "new_password": body.new_password,
        },
    )
