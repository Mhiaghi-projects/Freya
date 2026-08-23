#!/usr/bin/env python3
"""Pide a secrets un certificado nuevo para un servicio, firmado por la CA
interna, y lo escribe en infra/certs/<servicio>/. Uso interno de
Update-FreyaCertificate (infra/powershell/FreyaServices.psm1) -- nunca a
mano.

    python3 infra/scripts/renew_cert.py <servicio>

Necesita infra/secrets/freya-ops/api_secret montado en /run/secrets/api_secret
y red hacia freya-mesh. infra/certs/<servicio>/ se monta en /out para poder
escribir ahí.
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
    if len(sys.argv) != 2:
        print("uso: renew_cert.py <servicio>", file=sys.stderr)
        return 1
    service = sys.argv[1]

    token = get_token()
    req = urllib.request.Request(
        f"{SECRETS_URL}/certs/{service}/issue",
        data=b"{}",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
            result = json.loads(resp.read())["data"]
    except urllib.error.HTTPError as exc:
        print(f"fallo emitiendo el certificado: {exc.code} {exc.read().decode()}", file=sys.stderr)
        return 1

    out_dir = Path("/out")
    (out_dir / "tls.key").write_text(result["tls_key"], encoding="utf-8")
    (out_dir / "tls.crt").write_text(result["tls_crt"], encoding="utf-8")
    (out_dir / "ca.crt").write_text(result["ca_crt"], encoding="utf-8")
    print(f"certificado renovado para '{service}' en {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
