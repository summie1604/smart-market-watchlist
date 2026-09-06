.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install workspace dependencies
	cd ../.. && bun install

build: ## Type-check the mobile proof
	bun run build

test: ## Run mobile client tests
	bun test

lint: ## Type-check the mobile proof
	bun run build

format: ## Format TypeScript sources
	cd ../web && bun run prettier --write ../mobile/App.tsx "../mobile/src/**/*.ts" "../mobile/tests/**/*.ts"

run: ## Start the Expo development server
	bun run start

clean: ## Remove Expo and TypeScript build metadata
	rm -rf .expo
	rm -f tsconfig.tsbuildinfo

distclean: clean ## Remove workspace-installed dependencies
	rm -rf node_modules

.PHONY: help install build test lint format run clean distclean
