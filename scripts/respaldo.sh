#!/usr/bin/env bash
# Copia de la base (formato personalizado de pg_dump) en respaldos/, que git ignora.
# Las copias con datos reales NUNCA se suben al repositorio: es público.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p respaldos
destino="respaldos/estudia-$(date +%Y%m%d-%H%M%S).dump"
if [ -n "${RESPALDO_URL:-}" ]; then            # base remota (rol de administración): pg_dump local
  pg_dump --format=custom --no-owner --file "$destino" "$RESPALDO_URL"
else                                            # base local del contenedor
  docker compose exec -T db pg_dump -U estudia --format=custom --no-owner estudia > "$destino"
fi
echo "$destino"
