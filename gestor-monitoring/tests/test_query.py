"""Pruebas puras de app/domain/query.py, sin red."""

from __future__ import annotations

from app.domain.query import build_promql


def test_metrica_amigable_se_traduce_y_filtra_por_servicio() -> None:
    promql = build_promql("request_rate", "storage")
    assert 'service="storage"' in promql
    assert "freya_http_requests_total" in promql


def test_response_time_usa_histogram_quantile() -> None:
    promql = build_promql("response_time_ms", "git")
    assert "histogram_quantile" in promql
    assert 'service="git"' in promql


def test_metrica_no_amigable_se_trata_como_promql_cruda() -> None:
    raw = 'sum(up{service="storage"})'
    assert build_promql(raw, "storage") == raw


def test_traduccion_no_depende_del_orden_de_llamada() -> None:
    first = build_promql("error_rate", "auth")
    second = build_promql("error_rate", "secrets")
    assert 'service="auth"' in first
    assert 'service="secrets"' in second
    assert "auth" not in second
