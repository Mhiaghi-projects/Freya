#!/usr/bin/env python3
"""Descarga un volcado del bucket 'backups' de storage a un fichero local.
Uso interno de Restore-FreyaDatabaseCheck
(infra/powershell/FreyaServices.psm1) -- nunca se invoca a mano.

    python3 infra/scripts/backup_download.py <clave> <fichero-local>

Necesita infra/secrets/freya-ops/api_secret montado en
/run/secrets/api_secret y red hacia freya-mesh.
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


def main() -> int:
    if len(sys.argv) != 3:
        print("uso: backup_download.py <clave> <fichero-local>", file=sys.stderr)
        return 1
    key, local_file = sys.argv[1:3]

    token = get_token()
    req = urllib.request.Request(
        f"{STORAGE_URL}/storage/{BUCKET}/{key}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            content = resp.read()
    except urllib.error.HTTPError as exc:
        print(f"fallo la descarga: {exc.code} {exc.read().decode()}", file=sys.stderr)
        return 1

    Path(local_file).write_bytes(content)
    print(f"descargado {BUCKET}/{key} ({len(content)} bytes) a {local_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
