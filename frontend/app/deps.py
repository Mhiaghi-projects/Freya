"""Dependencias FastAPI reutilizables del servicio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from freya_common import FreyaError, MissingCredentials, ServiceClient

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass
class WebSession:
    claims: dict[str, Any]
    access_token: str


def set_session_cookies(
    response: Response, settings: Settings, *, access_token: str, refresh_token: str
) -> None:
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=settings.refresh_cookie_days * 86400,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.access_cookie_name, path="/")
    response.delete_cookie(settings.refresh_cookie_name, path="/")


async def _refresh(
    request: Request, response: Response, settings: Settings, refresh_token: str
) -> WebSession | None:
    """Intercambia el refresh token por un access token nuevo, en silencio
    -- el navegador nunca ve ninguno de los dos, sólo las cookies httponly
    que esta función reescribe."""
    auth = ServiceClient(settings.auth_url, "frontend", request.app.state.http)
    try:
        body = await auth.post(
            "/api/v1/auth/refresh-token", json={"refresh_token": refresh_token}
        )
    except FreyaError:
        return None
    data = ServiceClient.data(body)
    set_session_cookies(
        response,
        settings,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
    )
    claims = await request.app.state.verifier.verify(data["access_token"])
    return WebSession(claims=claims, access_token=data["access_token"])


async def web_session(request: Request, response: Response) -> WebSession:
    """Sesión del navegador vía cookies httponly. Si el access token caducó
    pero el refresh sigue vivo, renueva de forma transparente -- el
    front-end no tiene que saber que esto ocurrió."""
    settings = get_settings()
    access_token = request.cookies.get(settings.access_cookie_name)
    if access_token:
        try:
            claims = await request.app.state.verifier.verify(access_token)
            return WebSession(claims=claims, access_token=access_token)
        except FreyaError:
            pass

    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if refresh_token:
        session = await _refresh(request, response, settings, refresh_token)
        if session is not None:
            return session

    raise MissingCredentials("Sesión no iniciada o caducada")


WebSessionDep = Annotated[WebSession, Depends(web_session)]
