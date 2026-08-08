SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: setup dev dev-native down test lint typecheck seed demo e2e \
        db-upgrade db-downgrade db-revision fmt clean logs

## setup — install all workspace dependencies (TS + Python) and start infra
setup:
	pnpm install
	uv sync --all-packages
	docker compose up -d postgres redis minio
	@echo "Waiting for postgres to be healthy..."
	@until docker compose exec -T postgres pg_isready -U jkr -d jkr_ai_calling >/dev/null 2>&1; do sleep 1; done
	$(MAKE) db-upgrade
	@echo "Setup complete. Run 'make seed' then 'make dev'."

## dev — run the full stack via docker compose (rebuilds images as needed)
dev:
	docker compose up --build

## dev-native — run every service natively (faster inner loop than docker)
## Run each of these in its own terminal:
##   uv run --package jkr-api uvicorn app.main:app --reload --port 8000 (from services/api)
##   uv run --package jkr-voice-worker uvicorn app.main:app --reload --port 8100 (from services/voice-worker)
##   uv run --package jkr-campaign-worker dramatiq app.tasks -p 1 -t 1 (from services/campaign-worker)
##   uv run --package jkr-intelligence-worker dramatiq app.tasks -p 1 -t 1 (from services/intelligence-worker)
##   uv run --package jkr-integration-worker dramatiq app.tasks -p 1 -t 1 (from services/integration-worker, once it exists)
##   pnpm --filter web dev (from repo root)
dev-native:
	@echo "See Makefile 'dev-native' target comments for the per-service commands."

down:
	docker compose down

logs:
	docker compose logs -f

## test — run all test suites (Python pytest across the uv workspace, TS via turbo)
test:
	uv run pytest
	pnpm test

## lint — ruff for Python, eslint for TS
lint:
	uv run ruff check packages services
	pnpm lint

## typecheck — mypy for Python, tsc for TS
typecheck:
	uv run mypy packages services
	pnpm typecheck

## fmt — format everything
fmt:
	uv run ruff format packages services
	pnpm format

## db-upgrade — apply Alembic migrations
db-upgrade:
	cd packages/db && MIGRATIONS_DATABASE_URL_SYNC=$${MIGRATIONS_DATABASE_URL_SYNC:-postgresql+psycopg://jkr:jkr_local_dev@localhost:55432/jkr_ai_calling} uv run alembic upgrade head

db-downgrade:
	cd packages/db && MIGRATIONS_DATABASE_URL_SYNC=$${MIGRATIONS_DATABASE_URL_SYNC:-postgresql+psycopg://jkr:jkr_local_dev@localhost:55432/jkr_ai_calling} uv run alembic downgrade -1

## db-revision — autogenerate a new migration; usage: make db-revision m="add foo"
db-revision:
	cd packages/db && MIGRATIONS_DATABASE_URL_SYNC=$${MIGRATIONS_DATABASE_URL_SYNC:-postgresql+psycopg://jkr:jkr_local_dev@localhost:55432/jkr_ai_calling} uv run alembic revision --autogenerate -m "$(m)"

## seed — load the three demo workspaces (Aaha Dental, Adarsh Educational, JKR Creatives)
seed:
	uv run --package jkr-db python -m jkr_db.seed

## demo — end-to-end scripted walkthrough of the spec §33 demo flow against a running stack
demo:
	uv run --package jkr-db python scripts/run_demo.py

## e2e — Playwright browser test of the UI-navigable demo flow (needs the full stack running — see dev-native)
e2e:
	cd tests/e2e && pnpm exec playwright test

clean:
	docker compose down -v
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name ".venv" -type d -prune -exec rm -rf {} +
	rm -rf apps/web/.next node_modules apps/*/node_modules packages/*/node_modules
