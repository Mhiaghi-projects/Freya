"""Cabeceras de seguridad estándar en toda respuesta (OWASP Security
Misconfiguration): ningún servicio de Freya las ponía antes de esto.

Universal para los 10 servicios propios, JSON-only en 9 de ellos y el SPA
real en frontend -- la CSP es segura para ambos casos porque frontend no
usa scripts/estilos inline en ningún sitio (app/static/index.html sólo
tiene un <script src="app.js">, sin `style="..."` en ningún elemento;
app.js construye el DOM con createElement/setAttribute, nunca innerHTML
con contenido no de confianza -- ver docs/DECISIONS.md, repaso de
seguridad), así que no hace falta 'unsafe-inline' ni 'unsafe-eval'.

`setdefault`, no asignación directa: una ruta concreta que ya haya puesto
su propia cabecera (no hay ninguna hoy, pero por si acaso) gana.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # HSTS es inerte en un servicio que ningún navegador visita directo
    # (los 9 internos, sin puerto publicado) y real donde sí importa
    # (frontend, detrás de Traefik) -- más simple ponerla en todos que
    # tener dos rutas de creación de app distintas para esto solo.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": (
        "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
        "object-src 'none'"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response
