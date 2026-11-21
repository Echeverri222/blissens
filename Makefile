SHELL := /bin/bash
-include .env
export

.PHONY: golden-update respaldo restaurar-ensayo migrar-ensayo ensayo-supabase negocio migrar lint setup dev test seed reset importar cierre db-up stop usuario api-esquema panel panel-deps e2e

db-up:
	docker compose up -d --wait db
	@docker compose exec -T db psql -U estudia -d postgres -tc "select 1 from pg_database where datname='estudia_test'" | grep -q 1 || docker compose exec -T db psql -U estudia -d postgres -c "create database estudia_test"

panel-deps:
	@test -d panel/node_modules || (cd panel && npm ci --no-audit --no-fund)

panel: panel-deps
	cd panel && npm run build

setup:
	@test -f .env || cp .env.example .env
	uv sync
	cd panel && npm ci --no-audit --no-fund
	$(MAKE) panel
	$(MAKE) db-up
	uv run python -m estudia.migrate
	uv run python -m estudia.data seed
	@echo "Listo. Ejecuta: make dev"

dev: db-up panel-deps
	@mkdir -p .logs
	@echo "Panel: http://localhost:8000/panel | Paciente: http://localhost:8000/agendar | Simulador: http://localhost:8000/simulador | API: http://localhost:8000/docs"
	@echo "El panel se reconstruye al guardar; recarga el navegador para ver el cambio."
	@trap 'kill 0' INT TERM EXIT; \
	uv run uvicorn estudia.web.app:app --port 8000 --reload & \
	uv run python -m estudia.worker & \
	(cd panel && npm run build:watch) & \
	wait

golden-update: db-up
	GOLDEN_UPDATE=1 uv run pytest tests/test_golden.py

test: db-up panel-deps
	uv run pytest
	cd panel && npm run typecheck && npm run lint && npm test

e2e: db-up panel-deps
	cd panel && npx playwright install chromium && E2E=1 npm run e2e

seed: db-up
	uv run python -m estudia.migrate
	uv run python -m estudia.data seed

reset: db-up
	uv run python -m estudia.data reset

importar: db-up
	uv run python -m estudia.data importar

cierre: db-up
	uv run python -m estudia.indicators

usuario: db-up
	@uv run python -m estudia.usuarios $(ARGS)

api-esquema:
	uv run python -m estudia.api.esquema

negocio: db-up
	@uv run python -m estudia.negocios $(ARGS)

migrar: db-up
	@uv run python -m estudia.migrate $(ARGS)

lint:
	uv run ruff check .
	cd panel && npm run lint

stop:
	docker compose stop db

respaldo: db-up
	@./scripts/respaldo.sh

restaurar-ensayo: db-up
	@./scripts/restaurar-ensayo.sh $(COPIA)

# Ensaya las migraciones subir/bajar/subir sobre una base temporal
migrar-ensayo: db-up
	uv run pytest tests/test_aislamiento.py -k migraciones -q

# Ensayo de lo que distingue a Supabase (imagen de Postgres de Supabase): ver scripts/ensayo-supabase.sh
ensayo-supabase:
	@./scripts/ensayo-supabase.sh
