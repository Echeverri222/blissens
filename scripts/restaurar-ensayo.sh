#!/usr/bin/env bash
# Restaura una copia en una base TEMPORAL y corre las verificaciones del migrador (versión, extensiones, huellas,
# filas sin negocio) más un conteo de filas por tabla. Una copia que no se ha restaurado no es una copia.
set -euo pipefail
cd "$(dirname "$0")/.."
copia="${1:-$(ls -t respaldos/*.dump | head -1)}"
db="estudia_ensayo"
psql_local() { docker compose exec -T db psql -U estudia -d postgres -v ON_ERROR_STOP=1 "$@"; }
psql_local -c "drop database if exists $db" -c "create database $db"
trap 'psql_local -c "drop database if exists $db" >/dev/null' EXIT
docker compose exec -T db pg_restore -U estudia --no-owner -d "$db" < "$copia"
DATABASE_URL_ADMIN="postgresql://estudia:estudia@localhost:5433/$db" uv run python -m estudia.migrate verificar
docker compose exec -T db psql -U estudia -d "$db" -tAc \
  "select 'negocio=' || count(*) from negocio union all select 'paciente=' || count(*) from paciente union all select 'cita=' || count(*) from cita"
echo "Restauración ensayada con éxito: $copia"
