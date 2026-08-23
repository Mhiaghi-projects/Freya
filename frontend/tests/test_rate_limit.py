"""Rate limiting por tenant en el gateway (docs/ROADMAP.md Fase 11)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from freya_common import SlidingWindowLimiter

from app.infra.rate_limit import TenantRateLimitMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        TenantRateLimitMiddleware,
        limiter=SlidingWindowLimiter(max_attempts=2, window_seconds=60),
    )

    @app.get("/api/thing")
    def thing() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy"}

    return app


def test_limita_tras_el_maximo() -> None:
    client = TestClient(_make_app())
    assert client.get("/api/thing").status_code == 200
    assert client.get("/api/thing").status_code == 200
    response = client.get("/api/thing")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_rutas_operativas_exentas() -> None:
    client = TestClient(_make_app())
    for _ in range(5):
        assert client.get("/health").status_code == 200
