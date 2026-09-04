.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	bun install

build: ## Type-check and build the site
	bun run astro check --minimumSeverity error && bun run astro build

test: ## Run all tests
	bun test

lint: ## Type-check
	bun run astro check --minimumSeverity error

format: ## Format code
	bun run prettier --write "src/**/*.{ts,tsx,astro,css}"

run: ## Run the dev server
	bun run astro dev --port 4321

clean: ## Remove build artifacts
	rm -rf dist .astro

distclean: clean ## Remove build artifacts and installed dependencies
	rm -rf node_modules

.PHONY: help install build test lint format run clean distclean
