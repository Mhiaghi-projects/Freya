#!/usr/bin/env python3
"""Sube un volcado de base de datos al bucket 'backups' de storage
(ROADMAP.md Fase 11 adelantada: "Backups de database y storage hacia el
propio storage"). Uso interno de Backup-FreyaDatabase
(infra/powershell/FreyaServices.psm1) -- nunca se invoca a mano.

    python3 infra/scripts/backup_upload.py <fichero-local> <service>/<clave>

Necesita infra/secrets/freya-ops/api_secret montado en
/run/secrets/api_secret y red hacia freya-mesh. Crea el bucket 'backups' si
no existe todavía (idempotente: 409 se trata como éxito).
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

AUTH_URL = "https://freya-auth:8002"
STORAGE_URL = "https://freya-storage:8004"
BUCKET = "backups"
CTX = ssl._create_unverified_context()


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


def ensure_bucket(token: str) -> None:
    req = urllib.request.Request(
        f"{STORAGE_URL}/storage/buckets/{BUCKET}",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="PUT",
    )
    try:
        urllib.request.urlopen(req, timeout=15, context=CTX)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise


def main() -> int:
    if len(sys.argv) != 3:
        print("uso: backup_upload.py <fichero-local> <clave>", file=sys.stderr)
        return 1
    local_file, key = sys.argv[1:3]
    content = Path(local_file).read_bytes()

    token = get_token()
    ensure_bucket(token)

    req = urllib.request.Request(
        f"{STORAGE_URL}/storage/{BUCKET}/{key}",
        data=content,
        headers={
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {token}",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            print(f"subido a storage: {BUCKET}/{key} ({len(content)} bytes) -- {resp.status}")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"fallo la subida: {exc.code} {exc.read().decode()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
