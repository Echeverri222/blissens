#!/usr/bin/env bash
# Ensayo contra la imagen de PostgreSQL de Supabase: migra, corre la suite con el rol de aplicación, comprueba que la
# API de datos no devuelve ninguna tabla y que pg_cron puede disparar /tick. Lo que NO se puede comprobar en local
# (intermediario de conexiones compartido, IPv6 de Render, pausa del proyecto gratuito) queda para el día del despliegue.
set -euo pipefail
cd "$(dirname "$0")/.."
C="docker compose -p estudia-supabase -f docker-compose.supabase.yml"
trap '$C down -v >/dev/null 2>&1' EXIT
$C up -d --wait db
adm() { $C exec -T db psql -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"; }
adm -tAc "select 'PostgreSQL ' || current_setting('server_version')"
adm -c "create database estudia_test" >/dev/null
for d in postgres estudia_test; do
  export DATABASE_URL_ADMIN="postgresql://postgres:postgres@localhost:54329/$d"
  uv run python -m estudia.migrate subir
done
export DATABASE_URL_ADMIN="postgresql://postgres:postgres@localhost:54329/postgres"
uv run python -m estudia.migrate verificar
echo "== Suite con el rol de aplicación (estudia_app) =="
TEST_DATABASE_URL="postgresql://estudia_app:estudia_app@localhost:54329/estudia_test" \
TEST_DATABASE_URL_ADMIN="postgresql://postgres:postgres@localhost:54329/estudia_test" uv run pytest -q
echo "== API de datos =="
$C exec -T -e PGPASSWORD=postgres db psql -h localhost -U supabase_admin -d postgres -c "alter role authenticator with password 'postgres'" >/dev/null
$C up -d api
for i in $(seq 1 30); do curl -sf localhost:54330/ >/dev/null && break; sleep 1; done
paths=$(curl -s localhost:54330/ | python3 -c "import json,sys; print(','.join(p for p in json.load(sys.stdin).get('paths', {}) if p != '/'))")
if [ -n "$paths" ]; then echo "La API de datos expone tablas: $paths"; exit 1; fi
echo "La API de datos no devuelve ninguna tabla."
echo "== pg_cron =="
adm -tAc "select 'pg_cron disponible: ' || (count(*) > 0) from pg_available_extensions where name='pg_cron'"
echo "Ensayo terminado."
