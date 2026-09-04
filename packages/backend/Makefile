.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv sync --all-groups

build: ## Type-check
	uv run ty check src/

test: ## Run all tests
	uv run pytest

lint: ## Lint and type-check
	uv run ruff format --check . && uv run ruff check . && uv run ty check src/

format: ## Format code
	uv run ruff format .

run: ## Run the API locally
	uv run uvicorn smart_watchlist.api.app:app --reload --port 8000

clean: ## Remove build artifacts
	rm -rf .pytest_cache .ruff_cache .coverage dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

distclean: clean ## Remove build artifacts and the virtualenv
	rm -rf .venv

.PHONY: help install build test lint format run clean distclean
