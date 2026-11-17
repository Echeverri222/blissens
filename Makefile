SHELL := /bin/bash
-include .env
export

.PHONY: setup dev test seed reset importar cierre db-up stop usuario api-esquema

db-up:
	docker compose up -d --wait db
	@docker compose exec -T db psql -U estudia -d postgres -tc "select 1 from pg_database where datname='estudia_test'" | grep -q 1 || docker compose exec -T db psql -U estudia -d postgres -c "create database estudia_test"

setup:
	@test -f .env || cp .env.example .env
	uv sync
	$(MAKE) db-up
	uv run python -m estudia.migrate
	uv run python -m estudia.data seed
	@echo "Listo. Ejecuta: make dev"

dev: db-up
	@mkdir -p .logs
	@echo "Aplicación: http://localhost:8000/agendar | Simulador: http://localhost:8000/simulador | Panel: http://127.0.0.1:8501 | API: http://localhost:8000/docs"
	@trap 'kill 0' INT TERM EXIT; \
	uv run uvicorn estudia.web.app:app --port 8000 --reload & \
	uv run python -m estudia.worker & \
	uv run streamlit run estudia/panel/app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false & \
	wait

test: db-up
	uv run pytest

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

stop:
	docker compose stop db
