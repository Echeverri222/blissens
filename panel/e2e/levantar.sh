#!/usr/bin/env bash
# Levanta la aplicación contra una base propia (estudia_e2e) reconstruida desde cero con datos ficticios.
set -euo pipefail
cd "$(dirname "$0")/../.."
export DATABASE_URL_ADMIN="${E2E_DATABASE_URL_ADMIN:-postgresql://estudia:estudia@localhost:5433/estudia_e2e}"
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql://estudia_app:estudia_app@localhost:5433/estudia_e2e}"
docker compose exec -T db psql -U estudia -d postgres -tc "select 1 from pg_database where datname='estudia_e2e'" | grep -q 1 \
  || docker compose exec -T db psql -U estudia -d postgres -c "create database estudia_e2e"
uv run python -m estudia.data reset >/dev/null
exec uv run uvicorn estudia.web.app:app --port 8100
