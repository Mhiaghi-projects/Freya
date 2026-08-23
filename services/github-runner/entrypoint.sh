#!/usr/bin/env bash
# Registra el runner contra GitHub (si no lo está ya) y lo arranca.
#
# El token de registro de un runner caduca en ~1h sin usar -- pedirlo a
# mano cada vez que este contenedor se recrea (restart: unless-stopped
# puede hacerlo en cualquier momento) sería frágil. En su lugar, este
# script pide uno fresco en cada arranque usando un PAT de larga duración
# (RUNNER_PAT_FILE), vía la API de GitHub -- ver
# infra/secrets/github-runner/README.md para cómo generarlo y qué scope
# necesita.
#
# Variables de entorno esperadas (ver docker-compose.yml):
#   RUNNER_URL       https://github.com/<owner>          (a nivel de cuenta/org)
#                     o https://github.com/<owner>/<repo>  (a nivel de un repo)
#   RUNNER_PAT_FILE  fichero con un PAT clásico, scope "repo" (repo) o
#                     "admin:org" (org) -- sólo se usa para pedir el token
#                     de registro, nunca se pasa a config.sh directamente.
#   RUNNER_NAME      nombre visible en GitHub (por defecto: nombre del host)
#   RUNNER_LABELS    etiquetas separadas por coma (por defecto: self-hosted,freya)

set -euo pipefail

: "${RUNNER_URL:?falta RUNNER_URL}"
: "${RUNNER_PAT_FILE:?falta RUNNER_PAT_FILE}"
if [ ! -f "$RUNNER_PAT_FILE" ]; then
  echo "[entrypoint] no existe $RUNNER_PAT_FILE -- ver infra/secrets/github-runner/README.md" >&2
  exit 1
fi
PAT="$(cat "$RUNNER_PAT_FILE")"
RUNNER_NAME="${RUNNER_NAME:-freya-runner-$(hostname)}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,freya}"

# RUNNER_URL es .../<owner> (org) o .../<owner>/<repo> (repo) -- el
# endpoint de registro difiere entre los dos.
owner_repo="${RUNNER_URL#https://github.com/}"
if [[ "$owner_repo" == */* ]]; then
  api_path="repos/${owner_repo}/actions/runners/registration-token"
else
  api_path="orgs/${owner_repo}/actions/runners/registration-token"
fi

fetch_registration_token() {
  curl -fsSL -X POST \
    -H "Authorization: Bearer ${PAT}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/${api_path}" \
    | jq -r '.token'
}

cd /home/runner

echo "[entrypoint] pidiendo token de registro..."
RUNNER_TOKEN="$(fetch_registration_token)"
if [ -z "$RUNNER_TOKEN" ] || [ "$RUNNER_TOKEN" = "null" ]; then
  echo "[entrypoint] no se pudo obtener el token de registro -- revisa el PAT y su scope" >&2
  exit 1
fi

if [ -f .runner ]; then
  echo "[entrypoint] ya registrado como '$RUNNER_NAME', se quita el registro anterior primero"
  ./config.sh remove --token "$RUNNER_TOKEN" || true
fi

./config.sh \
  --url "$RUNNER_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --work _work \
  --unattended \
  --replace

cleanup() {
  echo "[entrypoint] desregistrando runner..."
  local remove_token
  remove_token="$(fetch_registration_token)"
  ./config.sh remove --token "$remove_token" || true
}
trap cleanup EXIT

./run.sh
