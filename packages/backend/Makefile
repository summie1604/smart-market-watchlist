.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv sync --all-groups

build: api-types-check ## Type-check and verify the generated API contract
	uv run ty check src/

test: ## Run all tests
	uv run pytest

lint: ## Lint and type-check
	uv run ruff format --check . && uv run ruff check . && uv run ty check src/

format: ## Format code
	uv run ruff format .

api-types: ## Generate the shared TypeScript contract from OpenAPI
	uv run python scripts/generate_api_types.py ../shared/src/api.generated.ts

api-types-check: ## Fail if the committed TypeScript API contract is stale
	uv run python scripts/generate_api_types.py --check ../shared/src/api.generated.ts

llm-harness: ## Evaluate rule extraction without production writes or credentials
	uv run python scripts/run_llm_harness.py --provider rules

load-test: ## Measure local review, extraction, and chart paths against targets
	uv run python scripts/run_load_validation.py

run: ## Run the API locally
	uv run uvicorn smart_watchlist.api.app:app --reload --port 8000

attention-eval: ## Evaluate the attention engine against labelled cases
	uv run python scripts/run_attention_eval.py

clean: ## Remove build artifacts
	rm -rf .pytest_cache .ruff_cache .coverage dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

distclean: clean ## Remove build artifacts and the virtualenv
	rm -rf .venv

.PHONY: help install build test lint format api-types api-types-check llm-harness load-test run clean distclean
