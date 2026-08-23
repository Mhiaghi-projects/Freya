"""EnvelopeMiddleware no debe perder cabeceras repetidas (Set-Cookie) al
reenvolver una respuesta JSON -- bug real encontrado en vivo: frontend
emite dos cookies de sesión en /api/session/sign-in y sólo una sobrevivía,
porque dict(response.headers) descarta duplicados por construcción."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from freya_common.envelope import EnvelopeMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(EnvelopeMiddleware)

    @app.get("/two-cookies")
    def two_cookies(response: Response) -> dict:
        response.set_cookie("a", "1")
        response.set_cookie("b", "2")
        return {"ok": True}

    return app


def test_cookies_multiples_sobreviven_al_envoltorio() -> None:
    client = TestClient(_make_app())
    response = client.get("/two-cookies")
    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True}
    names = {c.split("=")[0] for c in response.headers.get_list("set-cookie")}
    assert names == {"a", "b"}
