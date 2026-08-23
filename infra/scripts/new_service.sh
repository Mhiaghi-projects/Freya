#!/usr/bin/env bash
# Crea un servicio nuevo a partir de la plantilla.
#
# NO se ejecuta en el host. Corre dentro del contenedor toolbox, invocado por
# freya.ps1:
#
#     .\freya.ps1 new storage
#
# El puerto sale del registro de infra\powershell\FreyaServices.psm1.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="${1:?uso: new_service.sh <nombre> <puerto>}"
PORT="${2:?uso: new_service.sh <nombre> <puerto>}"
# Cada servicio propio es su propio proyecto en la raíz del repo (su
# propio repo git, su propio pipeline) -- no un subdirectorio de
# services/. services/ sólo aloja los backends de terceros que no tienen
# código propio que versionar aparte (database, metrics, logs,
# dashboards).
DEST="$ROOT/$NAME"

if [[ -d "$DEST" ]]; then
  echo "Ya existe services/$NAME" >&2
  exit 1
fi

cp -r "$ROOT/templates/service-python" "$DEST"

# Sustituye los marcadores en todos los ficheros del servicio recién creado.
while IFS= read -r -d '' file; do
  sed -i "s/__SERVICE_NAME__/$NAME/g; s/__SERVICE_PORT__/$PORT/g" "$file"
done < <(find "$DEST" -type f -print0)

mkdir -p \
  "$ROOT/infra/certs/$NAME" \
  "$ROOT/infra/secrets/$NAME" \
  "$DEST/migrations" \
  "$ROOT/.github/workflows"

# Marcador para que Git conserve el directorio de migraciones vacío.
[[ -f "$DEST/migrations/.gitkeep" ]] || : > "$DEST/migrations/.gitkeep"

# Workflow de despliegue vía el runner autoalojado (services/github-runner/,
# docs/DECISIONS.md) -- en la RAIZ del repo (monorepo único, "go with
# mono"): GitHub Actions sólo descubre workflows en .github/workflows/ del
# repo, nunca en un subdirectorio -- ese fue el bug real la primera vez.
sed "s/__SERVICE_NAME__/$NAME/g" "$ROOT/templates/github-workflow/deploy.yml" \
  > "$ROOT/.github/workflows/deploy-$NAME.yml"

echo "Creado $NAME en el puerto $PORT"
