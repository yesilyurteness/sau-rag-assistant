.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test test-all check run up down logs validate-evals

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-fix lint issues and format code
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Static type check
	uv run mypy

test: ## Unit tests (no external services)
	uv run pytest -m "not integration" --cov --cov-report=term-missing

test-all: ## All tests (needs `make up` first)
	uv run pytest --cov

validate-evals: ## Validate the golden evaluation datasets
	uv run python -m evals.validate_dataset evals/datasets

check: lint typecheck test validate-evals ## Everything CI runs

run: ## Run the API locally with auto-reload
	uv run uvicorn app.main:app --reload --app-dir src

up: ## Start postgres, redis and the API
	docker compose up -d --build

down: ## Stop all services
	docker compose down

logs: ## Tail service logs
	docker compose logs -f
