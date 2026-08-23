"""Puente CGI hacia el binario real `git http-backend`
(docs/ARCHITECTURE.md §5: "propio: FastAPI sobre git http-backend").

http-backend habla CGI/1.1: variables de entorno + stdin para la petición,
y en stdout cabeceras "Clave: valor" seguidas de una línea en blanco y el
cuerpo — se traduce aquí a una respuesta HTTP normal.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


@dataclass
class CgiResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def _parse_cgi_output(raw: bytes) -> CgiResponse:
    # Cabeceras ASCII línea a línea desde el principio, hasta la primera
    # línea vacía -- nunca buscando el separador "\n\n"/"\r\n\r\n" en TODO
    # el búfer. El cuerpo de git-upload-pack es un packfile binario
    # (comprimido), y con un búfer de cientos de KB es cuestión de
    # probabilidad que contenga por casualidad esa misma secuencia de
    # bytes en algún punto -- si eso ocurre ANTES del separador real (o si
    # el separador real usa el otro estilo de fin de línea y sólo el del
    # cuerpo coincide), la búsqueda global corta el "head" en mitad del
    # binario, y bytes arbitrarios del packfile terminan tratados como
    # nombres de cabecera -- uvicorn los rechaza al mandarlos
    # ("Invalid HTTP header name"), tumbando la respuesta ya iniciada.
    # Encontrado en vivo clonando repos reales (cientos de KB), nunca en
    # los repos diminutos de la verificación original de la Fase 5.
    pos = 0
    headers: dict[str, str] = {}
    status = 200
    body = b""
    while True:
        newline = raw.find(b"\n", pos)
        if newline == -1:
            body = raw[pos:]
            break
        line = raw[pos:newline]
        pos = newline + 1
        if line in (b"", b"\r"):
            body = raw[pos:]
            break
        text = line.decode("latin-1").rstrip("\r")
        if ":" not in text:
            continue
        key, _, value = text.partition(":")
        key, value = key.strip(), value.strip()
        if key.lower() == "status":
            status = int(value.split(" ", 1)[0])
        else:
            headers[key] = value
    return CgiResponse(status, headers, body)


async def run_http_backend(
    *,
    project_root: Path,
    path_info: str,
    method: str,
    query_string: str,
    content_type: str,
    body: bytes,
    remote_user: str,
    git_protocol: str | None = None,
) -> CgiResponse:
    env = {
        **os.environ,
        "GIT_PROJECT_ROOT": str(project_root),
        "GIT_HTTP_EXPORT_ALL": "1",
        "PATH_INFO": path_info,
        "REQUEST_METHOD": method,
        "QUERY_STRING": query_string,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(body)),
        "REMOTE_USER": remote_user,
        "SERVER_PROTOCOL": "HTTP/1.1",
    }
    if git_protocol:
        # Cabecera "Git-Protocol" -> HTTP_GIT_PROTOCOL (convención CGI):
        # sin esto, http-backend nunca negocia protocolo v2 y un clon de un
        # repo vacío pierde el nombre de la rama por defecto (no hay
        # "ls-refs=unborn" que advertir en v0).
        env["HTTP_GIT_PROTOCOL"] = git_protocol
    proc = await asyncio.create_subprocess_exec(
        get_settings().git_binary,
        "http-backend",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=body)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git http-backend salió con {proc.returncode}: "
            f"{stderr.decode('utf-8', errors='replace')}"
        )
    return _parse_cgi_output(stdout)
