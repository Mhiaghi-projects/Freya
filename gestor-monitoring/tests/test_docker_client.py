"""Desmultiplexado de logs de Docker (app/domain/docker_client.py:_demux).
Sin contenedor de TTY, Docker mete cada línea en un frame con cabecera de
8 bytes (tipo de stream + tamaño big-endian) -- sin quitarla, el log sale
con basura binaria intercalada."""

from __future__ import annotations

from app.domain.docker_client import _demux


def _frame(stream_type: int, payload: bytes) -> bytes:
    return bytes([stream_type, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


def test_demux_un_frame() -> None:
    raw = _frame(1, b"hola\n")
    assert _demux(raw) == "hola\n"


def test_demux_varios_frames_stdout_y_stderr() -> None:
    raw = _frame(1, b"linea stdout\n") + _frame(2, b"linea stderr\n")
    assert _demux(raw) == "linea stdout\nlinea stderr\n"


def test_demux_vacio() -> None:
    assert _demux(b"") == ""


def test_demux_frame_truncado_no_avienta_excepcion() -> None:
    # Una cabecera que promete más bytes de los que realmente llegaron
    # (respuesta cortada a medias) no debe intentar leer fuera del búfer.
    raw = _frame(1, b"linea completa\n") + bytes([1, 0, 0, 0, 0, 0, 0, 50]) + b"a medias"
    assert _demux(raw) == "linea completa\n"
