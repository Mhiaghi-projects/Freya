"""Cliente mínimo sobre el socket de Docker: sólo lectura, sólo para
descubrir contenedores por la etiqueta freya.service (ROADMAP.md mon-02).

No usa el SDK oficial de Docker -- pesa mucho más de lo que hace falta
aquí. Un cliente HTTP sobre el socket Unix (docs/ARCHITECTURE.md: única
excepción a "nada toca Docker salvo freya.ps1", documentada en el README
de este servicio) es toda la superficie necesaria: listar contenedores y
leer sus etiquetas.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class DockerClient:
    def __init__(self, socket_path: str) -> None:
        transport = httpx.AsyncHTTPTransport(uds=socket_path)
        self._http = httpx.AsyncClient(transport=transport, base_url="http://docker")

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_service_containers(self) -> list[dict[str, Any]]:
        """Contenedores con la etiqueta freya.service (corriendo o no), con
        su estado y las etiquetas de scrape (freya.metrics.port/path)."""
        filters = json.dumps({"label": ["freya.service"]})
        response = await self._http.get(
            "/containers/json", params={"all": "true", "filters": filters}
        )
        response.raise_for_status()

        containers = []
        for raw in response.json():
            labels = raw.get("Labels") or {}
            containers.append(
                {
                    "id": raw["Id"][:12],
                    "service": labels.get("freya.service"),
                    # Sin la etiqueta freya.tenant, es un servicio propio de
                    # la plataforma (pedido explícito del usuario: monitoreo
                    # por proyecto -- ver gestor-monitoring/app/domain/
                    # services.py y app/api/monitoring.py).
                    "tenant": labels.get("freya.tenant", "freya"),
                    "metrics_port": labels.get("freya.metrics.port"),
                    "metrics_path": labels.get("freya.metrics.path", "/metrics"),
                    # Esquema para /ready (health_monitor.py) y /metrics
                    # (scraper.py). Todo servicio propio habla HTTPS salvo
                    # excepción explícita (frontend, desde que Traefik
                    # termina TLS en el borde y le llega en HTTP plano por
                    # freya-mesh) -- se anuncia con freya.health.scheme.
                    "scheme": labels.get("freya.health.scheme", "https"),
                    "state": raw.get("State", "unknown"),
                    "status": raw.get("Status", ""),
                    "image": raw.get("Image", ""),
                }
            )
        return [c for c in containers if c["service"]]

    async def container_logs(self, container_id: str, *, since: int) -> str:
        """Logs de stdout/stderr desde `since` (epoch, exclusivo) hasta
        ahora. Docker multiplexa stdout/stderr en un único stream binario
        cuando el contenedor no tiene TTY (nunca lo tiene aquí -- ningún
        docker-compose.yml de Freya pide `tty: true`): cada frame trae una
        cabecera de 8 bytes (tipo de stream + tamaño big-endian) antes del
        texto real, hay que desmultiplexarlo o el "log" sale con basura
        binaria intercalada."""
        response = await self._http.get(
            f"/containers/{container_id}/logs",
            params={
                "stdout": "1",
                "stderr": "1",
                "since": str(since),
                "timestamps": "1",
            },
        )
        response.raise_for_status()
        return _demux(response.content)


_FRAME_HEADER_SIZE = 8


def _demux(raw: bytes) -> str:
    # Asume siempre framing multiplexado: ningún docker-compose.yml de
    # Freya pide "tty: true", así que el caso "sin TTY" (el único que
    # Docker sirve así) es el único real -- adivinar el formato a partir
    # del contenido no es fiable (texto plano de 8+ bytes puede parecer
    # una cabecera válida por casualidad).
    chunks: list[bytes] = []
    pos = 0
    while pos + _FRAME_HEADER_SIZE <= len(raw):
        size = int.from_bytes(raw[pos + 4 : pos + 8], "big")
        start = pos + _FRAME_HEADER_SIZE
        end = start + size
        if end > len(raw):
            break
        chunks.append(raw[start:end])
        pos = end
    return b"".join(chunks).decode("utf-8", errors="replace")
