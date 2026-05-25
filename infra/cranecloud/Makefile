# Crane Cloud deploy wrappers — HealthSync Uganda
#
# Usage:
#   make -C infra/cranecloud init
#   make -C infra/cranecloud deploy ENV=pilot
#   make -C infra/cranecloud update-backend ENV=pilot
#   make -C infra/cranecloud list ENV=pilot
#
# Or from infra/cranecloud/:
#   make deploy ENV=pilot
#
# Defaults to ENV=staging. Source of truth for what gets deployed is
# `manifest.yaml`; per-environment values live in `environments/<env>.env`.

ENV          ?= staging
ENV_FILE     := environments/$(ENV).env
ENV_TEMPLATE := environments/$(ENV).env.example

# Colour helpers — terminals without colour see no escape codes (TERM=dumb).
ifeq ($(shell test -t 1 && echo tty),tty)
  C_GREEN  := \033[32m
  C_RED    := \033[31m
  C_YELLOW := \033[33m
  C_BLUE   := \033[34m
  C_RESET  := \033[0m
else
  C_GREEN  :=
  C_RED    :=
  C_YELLOW :=
  C_BLUE   :=
  C_RESET  :=
endif

.PHONY: help init env-check deploy deploy-postgres deploy-redis deploy-backend deploy-frontend \
        update-postgres update-redis update-backend update-frontend list info logout clean

help:  ## Show this help (default target)
	@echo "$(C_BLUE)HealthSync Uganda — Crane Cloud deploy$(C_RESET)"
	@echo "Usage:  make <target> ENV=<staging|pilot|production>"
	@echo "Current ENV: $(C_YELLOW)$(ENV)$(C_RESET)"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  $(C_GREEN)%-22s$(C_RESET) %s\n", $$1, $$2}'

init:  ## First-time guidance for a new environment
	@echo "$(C_BLUE)One-time setup for ENV=$(ENV):$(C_RESET)"
	@echo
	@echo "  1. From your interactive shell (not from CI / non-tty):"
	@echo "     $(C_YELLOW)cranecloud auth user$(C_RESET)                # confirm authentication"
	@echo "     $(C_YELLOW)cranecloud projects list$(C_RESET)            # find or create the project"
	@echo
	@echo "  2. If the project doesn't exist yet, create it once:"
	@echo "     $(C_YELLOW)cranecloud projects create$(C_RESET)"
	@echo "     # follow prompts; suggested name: healthsync-uganda-$(ENV)"
	@echo
	@echo "  3. Copy the env template and fill in real values:"
	@echo "     $(C_YELLOW)cp $(ENV_TEMPLATE) $(ENV_FILE)$(C_RESET)"
	@echo "     # then edit $(ENV_FILE) — set CRANECLOUD_PROJECT_ID,"
	@echo "     # SECRET_KEY (32 random bytes), DATABASE_URL, REDIS_URL,"
	@echo "     # NIRA_*, DHIS2_*, OTel endpoint."
	@echo
	@echo "  4. Then:"
	@echo "     $(C_YELLOW)make deploy ENV=$(ENV)$(C_RESET)"
	@echo

env-check:  ## Verify the env file exists and is readable
	@if [ ! -f "$(ENV_FILE)" ]; then \
	  printf "$(C_RED)Missing $(ENV_FILE)$(C_RESET)\n"; \
	  printf "Copy the template: $(C_YELLOW)cp $(ENV_TEMPLATE) $(ENV_FILE)$(C_RESET) and fill in values.\n"; \
	  exit 1; \
	fi
	@if [ ! -r "$(ENV_FILE)" ]; then \
	  printf "$(C_RED)$(ENV_FILE) is not readable.$(C_RESET)\n"; \
	  exit 1; \
	fi
	@printf "$(C_GREEN)✓$(C_RESET) $(ENV_FILE) present\n"

deploy: env-check deploy-postgres deploy-redis deploy-backend deploy-frontend  ## Deploy postgres + redis + backend + frontend
	@printf "$(C_GREEN)✓$(C_RESET) Deploy complete for ENV=$(ENV)\n"
	@printf "Capture the returned APP_IDs above into $(ENV_FILE) as\n"
	@printf "  POSTGRES_APP_ID=<uuid>\n  REDIS_APP_ID=<uuid>\n  BACKEND_APP_ID=<uuid>\n  FRONTEND_APP_ID=<uuid>\n"
	@printf "Subsequent rollouts use $(C_YELLOW)make update-{postgres,redis,backend,frontend}$(C_RESET).\n"
	@printf "$(C_RED)REMINDER:$(C_RESET) Crane Cloud apps do NOT have documented persistent volumes.\n"
	@printf "Schedule a pg_dump → external object-store backup before this env holds real PHI.\n"
	@printf "See infra/cranecloud/README.md \"Persistence caveat for self-hosted DB\".\n"

deploy-postgres: env-check  ## Deploy a Postgres app (custom image with init.sql baked in)
	@printf "$(C_BLUE)→ Deploying Postgres (ENV=$(ENV))$(C_RESET)\n"
	@set -a; . ./$(ENV_FILE); set +a; \
	 if [ -z "$$POSTGRES_PASSWORD" ]; then \
	   printf "$(C_RED)POSTGRES_PASSWORD is empty in $(ENV_FILE).$(C_RESET) Generate one:\n"; \
	   printf "  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'\n"; \
	   exit 1; \
	 fi; \
	 cranecloud apps deploy \
	   --project_id "$$CRANECLOUD_PROJECT_ID" \
	   --name "$$POSTGRES_APP_NAME" \
	   --image "$$POSTGRES_IMAGE:$$POSTGRES_IMAGE_TAG" \
	   --port "$$POSTGRES_PORT" \
	   --replicas "$$POSTGRES_REPLICAS" \
	   -e "POSTGRES_USER=$$POSTGRES_USER" \
	   -e "POSTGRES_PASSWORD=$$POSTGRES_PASSWORD" \
	   -e "POSTGRES_DB=$$POSTGRES_DB"

deploy-redis: env-check  ## Deploy a Redis app (redis:7-alpine + requirepass + LRU)
	@printf "$(C_BLUE)→ Deploying Redis (ENV=$(ENV))$(C_RESET)\n"
	@set -a; . ./$(ENV_FILE); set +a; \
	 if [ -z "$$REDIS_PASSWORD" ]; then \
	   printf "$(C_RED)REDIS_PASSWORD is empty in $(ENV_FILE).$(C_RESET) Generate one:\n"; \
	   printf "  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'\n"; \
	   exit 1; \
	 fi; \
	 cranecloud apps deploy \
	   --project_id "$$CRANECLOUD_PROJECT_ID" \
	   --name "$$REDIS_APP_NAME" \
	   --image "$$REDIS_IMAGE:$$REDIS_IMAGE_TAG" \
	   --port "$$REDIS_PORT" \
	   --replicas "$$REDIS_REPLICAS" \
	   --command "sh -c \"exec redis-server --requirepass \\\"\$$REDIS_PASSWORD\\\" --maxmemory 256mb --maxmemory-policy allkeys-lru --appendonly no\"" \
	   -e "REDIS_PASSWORD=$$REDIS_PASSWORD"

deploy-backend: env-check  ## Deploy the FastAPI backend (one-time per env)
	@printf "$(C_BLUE)→ Deploying backend (ENV=$(ENV))$(C_RESET)\n"
	@set -a; . ./$(ENV_FILE); set +a; \
	 cranecloud apps deploy \
	   --project_id "$$CRANECLOUD_PROJECT_ID" \
	   --name "$$BACKEND_APP_NAME" \
	   --image "$$BACKEND_IMAGE:$$BACKEND_IMAGE_TAG" \
	   --port "$$BACKEND_PORT" \
	   --replicas "$$BACKEND_REPLICAS" \
	   -e "APP_ENV=$$APP_ENV" \
	   -e "APP_NAME=$$APP_NAME" \
	   -e "LOG_LEVEL=$$LOG_LEVEL" \
	   -e "SECRET_KEY=$$SECRET_KEY" \
	   -e "DATABASE_URL=$$DATABASE_URL" \
	   -e "REDIS_URL=$$REDIS_URL" \
	   -e "OTEL_EXPORTER_OTLP_ENDPOINT=$$OTEL_EXPORTER_OTLP_ENDPOINT" \
	   -e "OTEL_SERVICE_NAME=$$OTEL_SERVICE_NAME" \
	   -e "OTEL_TRACES_SAMPLER=$$OTEL_TRACES_SAMPLER" \
	   -e "NIRA_BASE_URL=$$NIRA_BASE_URL" \
	   -e "NIRA_API_KEY=$$NIRA_API_KEY" \
	   -e "DHIS2_BASE_URL=$$DHIS2_BASE_URL" \
	   -e "DHIS2_USERNAME=$$DHIS2_USERNAME" \
	   -e "DHIS2_PASSWORD=$$DHIS2_PASSWORD" \
	   -e "CIRCUIT_BREAKER_FAILURE_THRESHOLD=$$CIRCUIT_BREAKER_FAILURE_THRESHOLD" \
	   -e "CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS=$$CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS" \
	   -e "RETRY_MAX_ATTEMPTS=$$RETRY_MAX_ATTEMPTS" \
	   -e "RETRY_BASE_DELAY_MS=$$RETRY_BASE_DELAY_MS" \
	   -e "CORS_ALLOW_ORIGINS=$$CORS_ALLOW_ORIGINS"

deploy-frontend: env-check  ## Deploy the Next.js frontend (one-time per env)
	@printf "$(C_BLUE)→ Deploying frontend (ENV=$(ENV))$(C_RESET)\n"
	@set -a; . ./$(ENV_FILE); set +a; \
	 cranecloud apps deploy \
	   --project_id "$$CRANECLOUD_PROJECT_ID" \
	   --name "$$FRONTEND_APP_NAME" \
	   --image "$$FRONTEND_IMAGE:$$FRONTEND_IMAGE_TAG" \
	   --port "$$FRONTEND_PORT" \
	   --replicas "$$FRONTEND_REPLICAS" \
	   -e "NEXT_PUBLIC_API_BASE_URL=$$NEXT_PUBLIC_API_BASE_URL" \
	   -e "NEXT_PUBLIC_APP_NAME=$$NEXT_PUBLIC_APP_NAME"

update-postgres: env-check  ## Re-roll the existing Postgres app (image bump only — env changes require recreate)
	@set -a; . ./$(ENV_FILE); set +a; \
	 if [ -z "$$POSTGRES_APP_ID" ]; then \
	   printf "$(C_RED)POSTGRES_APP_ID is not set in $(ENV_FILE).$(C_RESET)\n"; \
	   printf "Run $(C_YELLOW)make list ENV=$(ENV)$(C_RESET) to find it.\n"; \
	   exit 1; \
	 fi; \
	 printf "$(C_BLUE)→ Updating Postgres $$POSTGRES_APP_ID (ENV=$(ENV))$(C_RESET)\n"; \
	 printf "$(C_YELLOW)WARNING:$(C_RESET) without persistent volumes this restarts on a fresh data dir.\n"; \
	 printf "Confirm a recent pg_dump exists before proceeding.\n"; \
	 cranecloud apps update "$$POSTGRES_APP_ID" \
	   --image "$$POSTGRES_IMAGE:$$POSTGRES_IMAGE_TAG"

update-redis: env-check  ## Re-roll the existing Redis app (e.g. password rotation)
	@set -a; . ./$(ENV_FILE); set +a; \
	 if [ -z "$$REDIS_APP_ID" ]; then \
	   printf "$(C_RED)REDIS_APP_ID is not set in $(ENV_FILE).$(C_RESET)\n"; \
	   printf "Run $(C_YELLOW)make list ENV=$(ENV)$(C_RESET) to find it, then add to the env file.\n"; \
	   exit 1; \
	 fi; \
	 printf "$(C_BLUE)→ Updating Redis $$REDIS_APP_ID (ENV=$(ENV))$(C_RESET)\n"; \
	 cranecloud apps update "$$REDIS_APP_ID" \
	   --image "$$REDIS_IMAGE:$$REDIS_IMAGE_TAG" \
	   --replicas "$$REDIS_REPLICAS" \
	   -e "REDIS_PASSWORD=$$REDIS_PASSWORD"

update-backend: env-check  ## Roll out a new backend image to the existing app
	@set -a; . ./$(ENV_FILE); set +a; \
	 if [ -z "$$BACKEND_APP_ID" ]; then \
	   printf "$(C_RED)BACKEND_APP_ID is not set in $(ENV_FILE).$(C_RESET)\n"; \
	   printf "Run $(C_YELLOW)make list ENV=$(ENV)$(C_RESET) to find it, then add to the env file.\n"; \
	   exit 1; \
	 fi; \
	 printf "$(C_BLUE)→ Updating backend $$BACKEND_APP_ID (ENV=$(ENV))$(C_RESET)\n"; \
	 cranecloud apps update "$$BACKEND_APP_ID" \
	   --image "$$BACKEND_IMAGE:$$BACKEND_IMAGE_TAG" \
	   --replicas "$$BACKEND_REPLICAS"

update-frontend: env-check  ## Roll out a new frontend image to the existing app
	@set -a; . ./$(ENV_FILE); set +a; \
	 if [ -z "$$FRONTEND_APP_ID" ]; then \
	   printf "$(C_RED)FRONTEND_APP_ID is not set in $(ENV_FILE).$(C_RESET)\n"; \
	   printf "Run $(C_YELLOW)make list ENV=$(ENV)$(C_RESET) to find it, then add to the env file.\n"; \
	   exit 1; \
	 fi; \
	 printf "$(C_BLUE)→ Updating frontend $$FRONTEND_APP_ID (ENV=$(ENV))$(C_RESET)\n"; \
	 cranecloud apps update "$$FRONTEND_APP_ID" \
	   --image "$$FRONTEND_IMAGE:$$FRONTEND_IMAGE_TAG" \
	   --replicas "$$FRONTEND_REPLICAS"

list: env-check  ## List apps in the configured Crane Cloud project
	@set -a; . ./$(ENV_FILE); set +a; \
	 cranecloud apps list --project_id "$$CRANECLOUD_PROJECT_ID"

info: env-check  ## Get details of one app (pass APP_ID=...)
	@if [ -z "$(APP_ID)" ]; then \
	  printf "$(C_RED)APP_ID required.$(C_RESET) Example: make info ENV=$(ENV) APP_ID=<uuid>\n"; \
	  exit 1; \
	fi
	@cranecloud apps info $(APP_ID)

logout:  ## Log out of the Crane Cloud CLI session
	@cranecloud auth logout

clean:  ## Remove any locally cached deploy artefacts (does not affect Crane Cloud)
	@find . -name "*.deploy.log" -type f -delete 2>/dev/null || true
	@printf "$(C_GREEN)✓$(C_RESET) Local cleanup done\n"

.DEFAULT_GOAL := help
