"""Librería común de los servicios de Freya."""

from .app import create_app
from .auth_client import (
    INTERNAL_AUDIENCE,
    JwksCache,
    ServiceTokenProvider,
    TokenVerifier,
    require_permissions,
)
from .config import BaseServiceSettings
from .context import (
    current_request_id,
    current_service,
    current_subject,
    current_tenant,
    new_request_id,
)
from .envelope import NO_ENVELOPE_HEADER
from .errors import (
    AccountLocked,
    BadRequest,
    Conflict,
    DependencyUnavailable,
    Forbidden,
    FreyaError,
    MissingCredentials,
    NotFound,
    PayloadTooLarge,
    QuotaExceeded,
    RateLimited,
    TenantInactive,
    TenantMismatch,
    TokenExpired,
    TokenInvalid,
    TokenRevoked,
    Unauthorized,
    UnprocessableEntity,
    UpstreamTimeout,
)
from .gestor_db import gdb_mutate, gdb_query
from .http import ServiceClient, build_http_client
from .ids import new_id, ulid
from .logging import configure_logging
from .migrations import MigrationRunner
from .rate_limit import SlidingWindowLimiter

__version__ = "1.0.0"

__all__ = [
    "AccountLocked",
    "BadRequest",
    "BaseServiceSettings",
    "Conflict",
    "DependencyUnavailable",
    "Forbidden",
    "FreyaError",
    "INTERNAL_AUDIENCE",
    "JwksCache",
    "MigrationRunner",
    "MissingCredentials",
    "NO_ENVELOPE_HEADER",
    "NotFound",
    "PayloadTooLarge",
    "QuotaExceeded",
    "RateLimited",
    "ServiceClient",
    "ServiceTokenProvider",
    "SlidingWindowLimiter",
    "TenantInactive",
    "TenantMismatch",
    "TokenExpired",
    "TokenInvalid",
    "TokenRevoked",
    "TokenVerifier",
    "Unauthorized",
    "UnprocessableEntity",
    "UpstreamTimeout",
    "build_http_client",
    "configure_logging",
    "create_app",
    "current_request_id",
    "current_service",
    "current_subject",
    "current_tenant",
    "gdb_mutate",
    "gdb_query",
    "new_id",
    "new_request_id",
    "require_permissions",
    "ulid",
]
