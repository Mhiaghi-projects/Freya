#!/usr/bin/env bash
# Despliega un servicio desde dentro del runner (docs/DECISIONS.md).
#
# Docker-outside-of-Docker, gotcha real encontrado en vivo: cuando este
# contenedor invoca "docker compose", las rutas relativas de "volumes:"
# (../infra/certs/<servicio>, ../infra/secrets/<servicio>) se resuelven
# usando la vista de ficheros DE ESTE CONTENEDOR (/workspace/infra/...) --
# pero quien de verdad monta esos volúmenes es el DAEMON de Docker Desktop
# en el host, que no tiene nada en /workspace/... (esa ruta sólo existe
# dentro de este contenedor). Resultado: Docker crea un directorio vacío
# en vez de fallar, y freya-secrets/freya-storage/etc arrancan sin sus
# certificados.
#
# Confirmado en vivo que el daemon SÍ resuelve bien una ruta Windows
# literal (D:\Proyectos\Freya\...) aunque la pida un contenedor anidado --
# la traducción de rutas de Docker Desktop es por formato, no por quién
# la pide. build: context, en cambio, ya funcionaba bien (BuildKit
# transmite el contexto como contenido de fichero, no como referencia de
# ruta que resuelva el daemon) -- por eso lint/test/security_scan ya
# pasaban y sólo "docker compose up" fallaba.
#
# Arreglo: una copia del docker-compose.yml, en el MISMO directorio (para
# que "build: context: .." siga apuntando bien a la raíz del repo), con
# "../infra" reescrito a la ruta Windows real. Se borra al terminar.

set -euo pipefail

SERVICE="${1:?uso: deploy-service.sh <servicio>}"
# Todo barra normal, nunca "\": confirmado en vivo que el daemon lo
# resuelve igual de bien, y evita el lío real de escapar backslashes a
# través de bash + sed (D:\Proyectos\Freya llegó a sed como D:ProyectosFreya
# -- sed trata "\P"/"\F" en el reemplazo como escapes de un carácter
# normal y se come la barra, no es un carácter literal sin más).
WIN_ROOT='D:/Proyectos/Freya'
SRC="$SERVICE/docker-compose.yml"
OUT="$SERVICE/.deploy-compose.yml"

trap 'rm -f "$OUT"' EXIT

sed "s|\.\./infra|${WIN_ROOT}/infra|g" "$SRC" > "$OUT"

docker compose --project-name freya -f "$OUT" --env-file .env up -d --build

# "docker compose up -d" sólo confirma que el contenedor ARRANCÓ, no que
# se quedó sano -- encontrado en vivo: el deploy roto de storage (antes
# de este arreglo) salió "Succeeded" en GitHub Actions con el contenedor
# en crash-loop por detrás. Se espera aquí al healthcheck que cada
# Dockerfile de Freya ya define, para que un despliegue roto de verdad
# falle el paso (y el run en GitHub salga en rojo, no en falso verde).
CONTAINER="freya-$SERVICE"
for _ in $(seq 1 30); do
  status="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "sin healthcheck")"
  case "$status" in
    healthy) echo "$CONTAINER: sano"; exit 0 ;;
    unhealthy) echo "$CONTAINER: unhealthy tras el despliegue" >&2; docker logs --tail 30 "$CONTAINER" >&2; exit 1 ;;
    "sin healthcheck") echo "$CONTAINER: sin healthcheck definido, no se puede verificar"; exit 0 ;;
  esac
  sleep 2
done
echo "$CONTAINER: no llegó a 'healthy' a tiempo (última: $status)" >&2
docker logs --tail 30 "$CONTAINER" >&2
exit 1
