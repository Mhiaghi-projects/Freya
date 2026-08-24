"""SecurityHeadersMiddleware debe poner las cabeceras estándar en toda
respuesta, y sobrevivir al reenvuelto de EnvelopeMiddleware -- por eso se
registra como la más externa de las dos (ver app.py)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from freya_common.envelope import EnvelopeMiddleware
from freya_common.security_headers import SecurityHeadersMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(EnvelopeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    return app


def test_cabeceras_de_seguridad_presentes() -> None:
    client = TestClient(_make_app())
    response = client.get("/ping")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_cabeceras_sobreviven_al_reenvuelto_de_envelope() -> None:
    # EnvelopeMiddleware reescribe la Response para respuestas JSON
    # (_rebuild_headers) -- si SecurityHeaders no fuera la más externa,
    # esto es justo el escenario donde sus cabeceras podrían perderse.
    client = TestClient(_make_app())
    response = client.get("/ping")
    assert response.json()["data"] == {"ok": True}
    assert response.headers["X-Frame-Options"] == "DENY"
