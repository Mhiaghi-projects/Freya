"""Pruebas puras del parseo de la salida CGI de git http-backend."""

from __future__ import annotations

from app.domain.cgi_bridge import _parse_cgi_output


def test_parsea_cabeceras_y_cuerpo() -> None:
    raw = (
        b"Content-Type: application/x-git-upload-pack-advertisement\n"
        b"Cache-Control: no-cache\n"
        b"\n"
        b"001e# service=git-upload-pack\n0000"
    )
    result = _parse_cgi_output(raw)
    assert result.status == 200
    assert result.headers["Content-Type"] == "application/x-git-upload-pack-advertisement"
    assert result.headers["Cache-Control"] == "no-cache"
    assert result.body == b"001e# service=git-upload-pack\n0000"


def test_status_explicito_se_respeta() -> None:
    raw = b"Status: 404 Not Found\nContent-Type: text/plain\n\nno encontrado"
    result = _parse_cgi_output(raw)
    assert result.status == 404
    assert result.body == b"no encontrado"


def test_cuerpo_binario_no_se_corrompe() -> None:
    body = bytes(range(256)) * 4
    raw = b"Content-Type: application/x-git-receive-pack-result\n\n" + body
    result = _parse_cgi_output(raw)
    assert result.body == body
