.PHONY: help stack stack-down backend frontend seed reset preflight test typecheck lint full

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

stack: ## Start Postgres + Redis only (for local backend/frontend dev)
	@scripts/dev-stack.sh

stack-down: ## Stop all docker-compose services
	@docker compose down

full: ## Bring up the entire stack via Docker Compose (Postgres, Redis, backend, frontend)
	@docker compose --profile full up --build

backend: ## Run the backend with auto-reload (requires `make stack`)
	@cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend: ## Run the Next.js dev server (requires `make backend`)
	@cd frontend && bun run dev

seed: ## Seed demo data — idempotent
	@cd backend && uv run python -m app.seed.run

reset: ## Drop the DB, flush Redis, re-seed (useful between rehearsals)
	@scripts/demo-reset.sh

preflight: ## Verify every load-bearing service is up (run before the showcase)
	@scripts/preflight.sh

test: ## Run the backend test suite
	@cd backend && uv run pytest -q

typecheck: ## Frontend TypeScript check
	@cd frontend && bun run typecheck

lint: ## Backend ruff + frontend eslint
	@cd backend && uv run ruff check app
	@cd frontend && bun run lint
