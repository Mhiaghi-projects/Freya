#!/usr/bin/env bash
# Genera una clave de firma RSA nueva para auth y la sube a secrets
# (sec-05 extendido: la rotación queda administrada desde ahí, ver
# auth/app/infra/secrets_keys.py). La PRIMERA clave de auth sigue
# siendo un fichero -- ver docs/ARCHITECTURE.md §2.1 -- pero las
# siguientes no necesitan tocar el host en absoluto: auth las recoge
# solo en su próximo arranque.
#
# NO se ejecuta en el host. Corre dentro del toolbox, invocado por
# Update-FreyaSigningKey (infra/powershell/FreyaServices.psm1):
#
#     .\freya.ps1 rotate-signing-key auth
#
# Necesita infra/secrets/freya-ops/api_secret montado en
# /run/secrets/api_secret y red hacia freya-mesh.

set -euo pipefail

AUTH_URL="https://freya-auth:8002"
SECRETS_URL="https://freya-secrets:8003"

KEY_FILE="$(mktemp)"
trap 'rm -f "$KEY_FILE"' EXIT

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$KEY_FILE" 2>/dev/null

# Mismo cálculo de kid que auth/app/domain/keys.py: sha256 de la clave
# pública en DER, primeros 16 hex.
KID="$(openssl pkey -in "$KEY_FILE" -pubout -outform DER 2>/dev/null \
  | openssl dgst -sha256 -r | cut -d' ' -f1 | cut -c1-16)"

log() { printf '[rotate-signing-key] %s\n' "$*"; }
log "clave nueva generada, kid=$KID"

API_SECRET="$(cat /run/secrets/api_secret)"
KEY_PEM="$(cat "$KEY_FILE")"

python3 - "$KID" "$KEY_PEM" "$API_SECRET" <<'PYEOF'
import json
import ssl
import sys
import urllib.error
import urllib.request

kid, key_pem, api_secret = sys.argv[1], sys.argv[2], sys.argv[3]
ctx = ssl._create_unverified_context()


def call(method, url, token, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


body = json.dumps({"service": "freya-ops", "api_secret": api_secret}).encode()
req = urllib.request.Request(
    "https://freya-auth:8002/authenticate/service",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
    token = json.loads(resp.read())["data"]["access_token"]

status, resp_body = call(
    "POST",
    "https://freya-secrets:8003/secrets/freya",
    token,
    {
        "key": f"auth/signing_keys/{kid}",
        "value": key_pem,
        "type": "rsa_private",
        "description": "Clave de firma JWT de auth, rotada (sec-05)",
        "overwrite": False,
    },
)
if status != 201:
    print(f"fallo subiendo la clave a secrets: {status} {resp_body}", file=sys.stderr)
    raise SystemExit(1)
print(f"clave {kid} subida a secrets (auth/signing_keys/{kid})")
PYEOF

log "listo. auth la recoge en su proximo arranque: .\\freya.ps1 restart auth"
