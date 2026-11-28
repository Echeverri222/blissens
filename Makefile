SHELL := /bin/bash
-include .env
export

.PHONY: golden-asistente golden-asistente-vivo asistente-charla golden-update respaldo restaurar-ensayo migrar-ensayo ensayo-supabase negocio migrar lint setup dev test seed reset importar importar-anonimo cierre db-up stop usuario api-esquema panel panel-deps e2e

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

# Golden cases del asistente (tests/golden_asistente/README.md). Sin modelo: estructura, herramientas y contexto.
golden-asistente: db-up
	uv run pytest tests/test_golden_asistente.py -q

# Con el modelo real, sobre el mundo ficticio: ASISTENTE_EVAL_KEY=... make golden-asistente-vivo [K=especialista]
#   o en Bedrock: ASISTENTE_EVAL_PROVEEDOR=bedrock ASISTENTE_EVAL_MODELO=claude-sonnet-5-5 make golden-asistente-vivo
golden-asistente-vivo: db-up
	ASISTENTE_EN_VIVO=1 uv run pytest tests/test_golden_asistente.py -q -k "en_vivo $(if $(K),and $(K),)" ; \
	uv run python scripts/informe_golden_asistente.py

# Una pregunta libre al modelo real: make asistente-charla ACTOR=rios PREGUNTA="¿quién sigue? || ábreme esa cita"
asistente-charla: db-up
	ASISTENTE_PREGUNTA="$(PREGUNTA)" ASISTENTE_ACTOR="$(or $(ACTOR),marta)" uv run pytest tests/test_golden_asistente.py -q -s -k charla

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

# Datos reales con la forma de siempre pero sin nadie reconocible (solo local; para la demo). Añade ARGS=--anonimo-profesionales
importar-anonimo: db-up
	uv run python -m estudia.data importar --anonimo $(ARGS)

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
