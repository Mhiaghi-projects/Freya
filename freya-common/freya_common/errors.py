"""Catálogo de errores y sobre de respuesta unificado de Freya.

Ver docs/freya-api-contract.md §1.3 (sobre) y §1.7 (catálogo de códigos).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .context import current_request_id


class FreyaError(Exception):
    """Error de negocio con código estable (del catálogo) y estado HTTP."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


# --- Autenticación / autorización (§1.7) -----------------------------------
class MissingCredentials(FreyaError):
    status_code = 401
    code = "MISSING_CREDENTIALS"


class Unauthorized(FreyaError):
    """Credenciales presentes pero incorrectas."""

    status_code = 401
    code = "INVALID_CREDENTIALS"


class TokenExpired(FreyaError):
    status_code = 401
    code = "TOKEN_EXPIRED"


class TokenInvalid(FreyaError):
    status_code = 401
    code = "TOKEN_INVALID"


class TokenRevoked(FreyaError):
    status_code = 401
    code = "TOKEN_REVOKED"


class Forbidden(FreyaError):
    status_code = 403
    code = "INSUFFICIENT_PERMISSIONS"


class TenantMismatch(FreyaError):
    status_code = 403
    code = "TENANT_MISMATCH"


class TenantInactive(FreyaError):
    status_code = 403
    code = "TENANT_INACTIVE"


class AccountLocked(FreyaError):
    status_code = 403
    code = "ACCOUNT_LOCKED"


# --- Validación --------------------------------------------------------
class UnprocessableEntity(FreyaError):
    status_code = 422
    code = "VALIDATION_ERROR"


class BadRequest(FreyaError):
    status_code = 400
    code = "INVALID_FORMAT"


class NotFound(FreyaError):
    status_code = 404
    code = "RESOURCE_NOT_FOUND"


class Conflict(FreyaError):
    status_code = 409
    code = "DUPLICATE_RESOURCE"


# --- Límites -------------------------------------------------------------
class RateLimited(FreyaError):
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"


class QuotaExceeded(FreyaError):
    status_code = 403
    code = "QUOTA_EXCEEDED"


class PayloadTooLarge(FreyaError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


# --- Infraestructura -------------------------------------------------------
class DependencyUnavailable(FreyaError):
    status_code = 503
    code = "UPSTREAM_UNAVAILABLE"


class UpstreamTimeout(FreyaError):
    status_code = 504
    code = "UPSTREAM_TIMEOUT"


def _meta() -> dict[str, Any]:
    return {"request_id": current_request_id(), "timestamp": int(time.time())}


def _error_payload(code: str, message: str, details: Any) -> dict[str, Any]:
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details},
        "meta": _meta(),
    }


_HTTP_STATUS_CODE = {
    400: "INVALID_FORMAT",
    401: "INVALID_CREDENTIALS",
    403: "INSUFFICIENT_PERMISSIONS",
    404: "RESOURCE_NOT_FOUND",
    405: "INVALID_FORMAT",
    409: "DUPLICATE_RESOURCE",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
}


def install_error_handlers(app: FastAPI) -> None:
    """Registra los manejadores que garantizan el sobre único de error."""

    @app.exception_handler(FreyaError)
    async def _freya(_: Request, exc: FreyaError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "issue": err["type"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                "VALIDATION_ERROR",
                "La petición no supera la validación de esquema",
                details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODE.get(exc.status_code, "INTERNAL_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, str(exc.detail), None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # El detalle real va al log, nunca al cliente.
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                "INTERNAL_ERROR", "Error interno del servicio", None
            ),
        )
