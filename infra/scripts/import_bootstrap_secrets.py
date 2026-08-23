#!/usr/bin/env python3
"""Echa una copia de cada credencial de arranque (infra/secrets/<servicio>/*)
al vault de secrets, bajo el namespace "bootstrap/" -- para que quede
administrada por secrets (auditoría, futura rotación desde un único sitio)
aunque el fichero en disco tenga que seguir existiendo.

Por qué el fichero no se borra (a diferencia de infra/certs/ca/ca.key):
cada uno de estos ficheros es la clave compartida que un servicio necesita
para hacer su PRIMERA llamada autenticada -- a auth, o (postgres_password)
para hablar el protocolo nativo de PostgreSQL antes de que exista ninguna
sesión HTTPS. No hay ninguna llamada a secrets posible todavía en ese
momento: pedírselo a secrets exigiría ya estar autenticado, que es
exactamente lo que este fichero resuelve. La CA sí se pudo borrar porque
`secrets` puede EMITIR un certificado nuevo bajo demanda; ninguno de estos
valores se puede volver a derivar -- son secretos aleatorios, no algo que
secrets sepa reconstruir.

master_key (services/secrets/) es la única excepción real: ni siquiera se
importa aquí, porque es la clave que cifra todo lo demás en el vault --
nada puede cifrarla salvo ella misma.

    python3 infra/scripts/import_bootstrap_secrets.py

Necesita infra/secrets/freya-ops/api_secret montado en /run/secrets/api_secret,
red hacia freya-mesh, y el árbol infra/secrets/ completo montado de sólo
lectura en /bootstrap.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

AUTH_URL = "https://freya-auth:8002"
SECRETS_URL = "https://freya-secrets:8003"
CTX = ssl._create_unverified_context()
BOOTSTRAP_DIR = Path("/bootstrap")

# (servicio, fichero relativo, tipo de secreto). master_key deliberadamente
# no está en esta lista -- ver docstring del módulo.
_FILES: list[tuple[str, str, str]] = [
    ("auth", "api_secret", "api_key"),
    ("cicd", "api_secret", "api_key"),
    ("freya-ops", "api_secret", "api_key"),
    ("gestor-db", "api_secret", "api_key"),
    ("gestor-db", "postgres_password", "db_credentials"),
    ("gestor-monitoring", "api_secret", "api_key"),
    ("git", "api_secret", "api_key"),
    ("project-manager", "api_secret", "api_key"),
    ("secrets", "api_secret", "api_key"),
    ("storage", "api_secret", "api_key"),
    ("database", "postgres_password", "db_credentials"),
    ("dashboards", "admin_password", "api_key"),
]


def call(method: str, url: str, token: str, body: dict):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def get_token() -> str:
    api_secret = Path("/run/secrets/api_secret").read_text(encoding="utf-8").strip()
    data = json.dumps({"service": "freya-ops", "api_secret": api_secret}).encode()
    req = urllib.request.Request(
        f"{AUTH_URL}/authenticate/service",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
        return json.loads(resp.read())["data"]["access_token"]


def main() -> int:
    token = get_token()
    ok = True
    for service, filename, type_ in _FILES:
        path = BOOTSTRAP_DIR / service / filename
        if not path.is_file():
            print(f"  {service}/{filename}: no existe en disco, se omite")
            continue
        value = path.read_text(encoding="utf-8").strip()
        key = f"bootstrap/{service}/{filename}"
        status, body = call(
            "POST",
            f"{SECRETS_URL}/secrets/freya",
            token,
            {
                "key": key,
                "value": value,
                "type": type_,
                "description": f"Copia de arranque de {service}/{filename} "
                f"(el fichero en disco sigue siendo la fuente operativa)",
                "overwrite": False,
            },
        )
        if status == 201:
            print(f"  {key}: importado")
        elif status == 409:
            print(f"  {key}: ya existía, se omite")
        else:
            print(f"  {key}: fallo {status} {body}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
