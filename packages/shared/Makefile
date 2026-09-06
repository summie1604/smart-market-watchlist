.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install workspace dependencies
	cd ../.. && bun install

build: ## Type-check the generated contract package
	bun run build

test: ## Verify contract invariants
	bun test

lint: ## Type-check the package
	bun run build

format: ## Format TypeScript sources
	cd ../web && bun run prettier --write "../shared/src/**/*.ts" "../shared/tests/**/*.ts"

clean: ## Remove TypeScript build metadata
	rm -f tsconfig.tsbuildinfo

distclean: clean ## Remove workspace-installed dependencies
	rm -rf node_modules

.PHONY: help install build test lint format clean distclean
