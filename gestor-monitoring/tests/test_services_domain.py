"""app/domain/services.py: filtra por `project` (pedido explícito del
usuario -- cada proyecto ve sólo sus propios contenedores, nunca los de
otro tenant ni los de Freya salvo que ESE sea el proyecto pedido)."""

from __future__ import annotations

import httpx
import pytest
from freya_common import FreyaError, ServiceClient

from app.domain.services import get_service, list_services

_CONTAINERS = [
    {
        "id": "abc123",
        "service": "auth",
        "tenant": "freya",
        "metrics_port": "9000",
        "metrics_path": "/metrics",
        "scheme": "https",
        "state": "running",
        "status": "Up",
        "image": "freya/auth",
    },
    {
        "id": "def456",
        "service": "athenea-app",
        "tenant": "athenea",
        "metrics_port": "9000",
        "metrics_path": "/metrics",
        "scheme": "https",
        "state": "running",
        "status": "Up",
        "image": "freya/athenea",
    },
]


class _FakeDocker:
    async def list_service_containers(self) -> list[dict]:
        return _CONTAINERS


class _FakeMonitor:
    last_check: dict = {}


def _empty_gestor_db() -> ServiceClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {"rows": []}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ServiceClient("https://freya-gestor-db:8001", "gestor-monitoring", http)


async def test_list_services_filtra_por_project() -> None:
    result = await list_services(
        _FakeDocker(), _FakeMonitor(), _empty_gestor_db(), "freya", project="freya"
    )
    names = [s["service"] for s in result["services"]]
    assert names == ["auth"]


async def test_list_services_de_otro_proyecto_no_ve_freya() -> None:
    result = await list_services(
        _FakeDocker(), _FakeMonitor(), _empty_gestor_db(), "freya", project="athenea"
    )
    names = [s["service"] for s in result["services"]]
    assert names == ["athenea-app"]


async def test_list_services_proyecto_sin_contenedores_da_lista_vacia() -> None:
    result = await list_services(
        _FakeDocker(), _FakeMonitor(), _empty_gestor_db(), "freya", project="otro"
    )
    assert result["services"] == []


async def test_get_service_no_cruza_proyectos() -> None:
    with pytest.raises(FreyaError) as exc_info:
        await get_service(
            _FakeDocker(),
            _FakeMonitor(),
            _empty_gestor_db(),
            "freya",
            project="freya",
            service="athenea-app",
        )
    assert exc_info.value.status_code == 404
