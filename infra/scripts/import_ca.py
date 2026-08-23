#!/usr/bin/env python3
"""Importa la CA de desarrollo (infra/certs/ca/) al vault de secrets, una
sola vez (docs/ROADMAP.md Fase 3, punto 4). Uso interno de
New-FreyaInternalCA (infra/powershell/FreyaCore.psm1) -- nunca a mano.

    python3 infra/scripts/import_ca.py

Necesita infra/secrets/freya-ops/api_secret montado en /run/secrets/api_secret,
red hacia freya-mesh, y el propio infra/certs/ca/{ca.key,ca.crt} en el
workspace. Usa la API genérica de secretos (POST /secrets/freya) con
overwrite=False: si la CA ya se importó antes, no la sustituye en
silencio -- falla con 409 y el llamante lo trata como éxito (idempotente).
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
ROOT = Path(__file__).resolve().parents[2]


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


def seed(token: str, *, key: str, value: str, type_: str, description: str) -> None:
    status, body = call(
        "POST",
        f"{SECRETS_URL}/secrets/freya",
        token,
        {"key": key, "value": value, "type": type_, "description": description, "overwrite": False},
    )
    if status == 201:
        print(f"'{key}' importado")
    elif status == 409:
        print(f"'{key}' ya existía, se omite")
    else:
        print(f"fallo importando '{key}': {status} {body}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    ca_key = (ROOT / "infra" / "certs" / "ca" / "ca.key").read_text(encoding="utf-8")
    ca_crt = (ROOT / "infra" / "certs" / "ca" / "ca.crt").read_text(encoding="utf-8")

    token = get_token()
    seed(
        token,
        key="_internal_ca_key",
        value=ca_key,
        type_="ca_key",
        description="Clave privada de la CA interna de Freya",
    )
    seed(
        token,
        key="_internal_ca_cert",
        value=ca_crt,
        type_="ca_cert",
        description="Certificado público de la CA interna de Freya",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
