#!/usr/bin/env bash
# CA de desarrollo de Freya y certificados por servicio.
#
# NO se ejecuta en el host. Corre dentro del contenedor toolbox, invocado por
# freya.ps1 (comandos `init` y `new`). Para lanzarlo a mano:
#
#     .\freya.ps1 shell
#     bash infra/scripts/gen_dev_ca.sh
#
# Esto es un apaño de arranque. En la Fase 3, `secrets` asume la emisión de
# certificados y este script se retira.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERTS="$ROOT/infra/certs"
CA_DIR="$CERTS/ca"

# Servicios previstos por la arquitectura. Los puertos no se usan aquí, pero
# se mantienen para que la lista sea legible junto a docs/ARCHITECTURE.md.
KNOWN_SERVICES=(
  "gestor-db" "auth" "secrets" "storage" "git"
  "project-manager" "cicd" "gestor-monitoring"
  "gamification" "frontend" "traefik"
)

log() { printf '[certs] %s\n' "$*"; }

# En un bind mount de Windows, chmod puede no tener efecto. No es motivo para
# abortar: el aislamiento real lo da el contenedor.
try_chmod() { chmod "$@" 2>/dev/null || true; }

# El proceso de cada servicio corre como UID:GID 10001 (usuario "freya" del
# Dockerfile). Sin este chown, la clave queda de root y uvicorn no puede
# leerla dentro del contenedor aunque el bind mount la exponga.
try_chown() { chown "$@" 2>/dev/null || true; }

mkdir -p "$CA_DIR"

if [[ ! -f "$CA_DIR/ca.crt" ]]; then
  log "generando CA de desarrollo (validez 10 años)"
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout "$CA_DIR/ca.key" -out "$CA_DIR/ca.crt" \
    -subj "/C=CO/O=Freya/CN=Freya Development CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  try_chmod 600 "$CA_DIR/ca.key"
else
  log "CA ya existente, se reutiliza"
fi

# Lista final: los servicios previstos más cualquiera ya creado en services/,
# para que un servicio nuevo reciba su certificado sin tocar este fichero.
services=("${KNOWN_SERVICES[@]}")
if [[ -d "$ROOT/services" ]]; then
  for dir in "$ROOT/services"/*/; do
    [[ -d "$dir" ]] || continue
    name="$(basename "$dir")"
    [[ " ${services[*]} " == *" $name "* ]] || services+=("$name")
  done
fi

for service in "${services[@]}"; do
  dir="$CERTS/$service"
  mkdir -p "$dir"

  # La CA se copia siempre: es lo que el servicio usa para confiar en la malla.
  cp "$CA_DIR/ca.crt" "$dir/ca.crt"

  if [[ -f "$dir/tls.crt" ]]; then
    log "$service: certificado ya presente"
    continue
  fi

  openssl req -newkey rsa:2048 -nodes \
    -keyout "$dir/tls.key" -out "$dir/tls.csr" \
    -subj "/C=CO/O=Freya/CN=freya-$service" 2>/dev/null

  # Fichero real, no <(...) -- la sustitución de proceso via /dev/fd falla
  # de forma intermitente en el primer openssl x509 de un contenedor recién
  # arrancado (visto en vivo: aborta con set -e a mitad del bucle, dejando
  # un tls.crt vacío que el chequeo de "ya presente" trata como válido).
  extfile="$dir/tls.ext"
  printf 'subjectAltName=DNS:freya-%s,DNS:%s,DNS:localhost,IP:127.0.0.1\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth,clientAuth\n' \
    "$service" "$service" > "$extfile"

  # El SAN cubre el nombre del contenedor y el nombre corto del servicio.
  openssl x509 -req -in "$dir/tls.csr" -days 825 \
    -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" -CAcreateserial \
    -out "$dir/tls.crt" \
    -extfile "$extfile" \
    2>/dev/null

  rm -f "$dir/tls.csr" "$extfile"
  try_chown 10001:10001 "$dir/tls.key"
  try_chmod 600 "$dir/tls.key"
  log "$service: certificado emitido"
done

log "listo. Los certificados NO se versionan (ver .gitignore)"
