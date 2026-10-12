DC = docker compose
export UID := $(shell id -u)
export GID := $(shell id -g)

.PHONY: help env up down logs ps migrate migration downgrade test lint format shell psql clean

help: ## Show commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example (if missing)
	@test -f .env || cp .env.example .env

up: env ## Build & start the stack (dev or prod depending on .env)
	$(DC) up -d --build

down: ## Stop the stack
	$(DC) down

logs: ## Follow app logs
	$(DC) logs -f app

ps: ## Containers status
	$(DC) ps

migrate: ## Apply migrations + seed admin
	$(DC) run --rm migrate

migration: ## Create a migration: make migration m="add product table"
	$(DC) up -d db
	$(DC) run --rm --no-deps app alembic revision --autogenerate -m "$(m)"

downgrade: ## Revert the last migration
	$(DC) up -d db
	$(DC) run --rm --no-deps app alembic downgrade -1

test: ## Run tests (database <POSTGRES_DB>_test)
	$(DC) up -d db
	$(DC) run --rm --no-deps app pytest

lint: ## Lint
	$(DC) run --rm --no-deps app ruff check .

format: ## Format code
	$(DC) run --rm --no-deps app sh -c "ruff check --fix . && ruff format ."

shell: ## Shell inside the app container
	$(DC) exec app bash

psql: ## psql into the database
	$(DC) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

clean: ## Stop the stack and DELETE its volumes (database data)
	$(DC) down -v
