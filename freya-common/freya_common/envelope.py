"""Envoltura uniforme de respuesta (docs/freya-api-contract.md §1.3):

    {"success": true,  "data": ...,  "meta": {"request_id", "timestamp", ...}}
    {"success": false, "error": ..., "meta": {"request_id", "timestamp"}}

Los routers devuelven su dict de datos tal cual, como siempre; este
middleware lo envuelve al vuelo. Los manejadores de error de errors.py ya
devuelven el sobre completo con "success": false, así que aquí sólo se
envuelve lo que todavía no lo esté — nunca se envuelve dos veces.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .middleware import REQUEST_ID_HEADER, TENANT_HEADER

# /health, /ready y /metrics quedan fuera de /api/v1 y del sobre — son el
# contrato operativo de Docker/monitoring, no de la API (docs/CONVENTIONS.md).
_UNWRAPPED_PATHS = {"/health", "/health/deep", "/ready", "/metrics"}

# Vía de escape para rutas que devuelven bytes ajenos tal cual (storage
# sirviendo el contenido de un objeto, por ejemplo): el content-type de esos
# bytes lo elige quien subió el objeto, no esta API, así que puede ser
# "application/json" sin que el cuerpo sea una respuesta de la API — el
# sniffing por content-type no puede distinguir ambos casos. La propia ruta
# marca su Response con esta cabecera para saltarse el sobre siempre, pase
# lo que pase el content-type; el middleware la retira antes de responder
# al cliente para que la marca nunca sea visible fuera de aquí.
NO_ENVELOPE_HEADER = "X-Freya-No-Envelope"


# Cabeceras que la Response nueva recalcula por su cuenta (content-length
# según el cuerpo reescrito, content-type según media_type) -- todo lo demás
# de la original se preserva tal cual, incluidas las repetidas (Set-Cookie:
# dict(response.headers) las perdería, porque una clave de dict no puede
# repetirse -- una respuesta con dos cookies se quedaría con una sola).
_RECOMPUTED_HEADERS = {b"content-length", b"content-type"}


def _rebuild_headers(new_response: Response, original: Response) -> None:
    carried = [h for h in original.raw_headers if h[0] not in _RECOMPUTED_HEADERS]
    new_response.raw_headers = new_response.raw_headers + carried


def _meta(request: Request, response: Response) -> dict[str, Any]:
    # request_id/tenant se leen de la petición/respuesta, no de los
    # contextvars: BaseHTTPMiddleware no propaga sus mutaciones desde el
    # middleware interno (ContextMiddleware) hasta el código que corre
    # después de call_next() en éste, más externo. Un objeto normal
    # (headers) sí atraviesa esa frontera sin problema.
    meta: dict[str, Any] = {
        "request_id": response.headers.get(REQUEST_ID_HEADER, ""),
        "timestamp": int(time.time()),
    }
    if tenant := request.headers.get(TENANT_HEADER):
        meta["tenant_id"] = tenant
    return meta


class EnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if request.url.path in _UNWRAPPED_PATHS:
            return response

        if NO_ENVELOPE_HEADER in response.headers:
            del response.headers[NO_ENVELOPE_HEADER]
            return response

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        if not body:
            empty = Response(
                content=body, status_code=response.status_code, media_type=content_type
            )
            _rebuild_headers(empty, response)
            return empty

        try:
            data = json.loads(body)
        except ValueError:
            unwrapped = Response(
                content=body, status_code=response.status_code, media_type=content_type
            )
            _rebuild_headers(unwrapped, response)
            return unwrapped

        wrapped = data if isinstance(data, dict) and "success" in data else None
        if wrapped is None:
            wrapped = {"success": True, "data": data, "meta": _meta(request, response)}

        new_body = json.dumps(wrapped, default=str).encode("utf-8")
        enveloped = Response(
            content=new_body,
            status_code=response.status_code,
            media_type="application/json",
        )
        _rebuild_headers(enveloped, response)
        return enveloped
