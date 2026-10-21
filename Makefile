.PHONY: setup up down migrate seed api web test typecheck api-client

COMPOSE = docker compose -f infra/docker-compose.yml
PY = backend/.venv/bin

setup:  ## Install backend and frontend dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
	npm install

up:  ## Start Postgres, Redis and Mailpit
	$(COMPOSE) up -d --wait

down:
	$(COMPOSE) down

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:  ## Load checklist templates (safe to re-run)
	cd backend && .venv/bin/python -m app.scripts.seed

api:  ## FastAPI on http://localhost:8000 (docs at /docs)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:  ## Web app on http://localhost:5180
	npm run dev:web

test:
	cd backend && .venv/bin/pytest -q

typecheck:
	cd backend && .venv/bin/ruff check app tests
	npm run typecheck

api-client:  ## Regenerate the TypeScript client after changing the API
	npm run api:generate
