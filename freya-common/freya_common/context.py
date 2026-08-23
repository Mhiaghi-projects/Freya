"""Contexto por petición: request_id, tenant, servicio y sujeto autenticado.

Se guarda en ContextVar para que el logger y los clientes HTTP lo propaguen
sin tener que pasarlo por parámetro por toda la pila.
"""

from __future__ import annotations

from contextvars import ContextVar

from .ids import new_id

_request_id: ContextVar[str] = ContextVar("freya_request_id", default="")
_tenant: ContextVar[str] = ContextVar("freya_tenant", default="")
_service: ContextVar[str] = ContextVar("freya_service", default="")
_subject: ContextVar[str] = ContextVar("freya_subject", default="")


def new_request_id() -> str:
    return new_id("req")


def set_request_id(value: str | None) -> str:
    rid = value or new_request_id()
    _request_id.set(rid)
    return rid


def current_request_id() -> str:
    return _request_id.get()


def set_tenant(value: str | None) -> str:
    tenant = value or ""
    _tenant.set(tenant)
    return tenant


def current_tenant() -> str:
    return _tenant.get()


def set_service(value: str | None) -> str:
    service = value or ""
    _service.set(service)
    return service


def current_service() -> str:
    return _service.get()


def set_subject(value: str | None) -> str:
    subject = value or ""
    _subject.set(subject)
    return subject


def current_subject() -> str:
    return _subject.get()
