"""Comprobaciones mínimas que todo servicio de Freya debe pasar."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_health_responde_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"]
    assert body["version"]


def test_request_id_se_devuelve_siempre(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Request-ID"]


def test_request_id_entrante_se_propaga(client: TestClient) -> None:
    incoming = "req_11111111112222222222"
    response = client.get("/health", headers={"X-Request-ID": incoming})
    assert response.headers["X-Request-ID"] == incoming


def test_error_usa_el_sobre_comun(client: TestClient) -> None:
    response = client.get("/api/v1/ruta-que-no-existe")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert set(body["error"]) >= {"code", "message", "details"}
    assert "request_id" in body["meta"]


def test_ready_incluye_checks(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    assert "checks" in response.json()
