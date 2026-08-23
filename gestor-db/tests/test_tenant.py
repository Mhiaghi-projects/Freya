"""Resolución de schema por tenant (docs/freya-api-contract.md §4, §16.1)."""

from __future__ import annotations

import pytest
from freya_common import BadRequest, TenantMismatch

from app.domain.tenant import resolve_schema


def test_sin_schema_explicito_usa_el_tenant() -> None:
    assert resolve_schema("fortuna", None) == "fortuna"


def test_schema_con_nombre_del_propio_tenant() -> None:
    assert resolve_schema("fortuna", "fortuna_staging") == "fortuna_staging"


def test_schema_de_otro_tenant_es_tenant_mismatch() -> None:
    with pytest.raises(TenantMismatch):
        resolve_schema("fortuna", "potato")
    with pytest.raises(TenantMismatch):
        resolve_schema("fortuna", "potato_staging")


def test_tenant_invalido_es_bad_request() -> None:
    with pytest.raises(BadRequest):
        resolve_schema("Fortuna", None)
    with pytest.raises(BadRequest):
        resolve_schema("fortuna; DROP SCHEMA freya", None)
