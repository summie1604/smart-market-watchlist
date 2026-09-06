.DEFAULT_GOAL := help
PACKAGES := packages/backend packages/shared packages/web packages/mobile

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg install || exit 1; done


build: ## Build and type-check every package
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg build || exit 1; done

test: ## Run every package's tests
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg test || exit 1; done

lint: ## Lint and type-check every package
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg lint || exit 1; done

format: ## Format every package
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg format || exit 1; done

run: ## Run the API and web dev server together
	@$(MAKE) -C packages/backend run & $(MAKE) -C packages/web run & wait

run-api: ## Run the API only
	$(MAKE) -C packages/backend run

run-web: ## Run the web dev server only
	$(MAKE) -C packages/web run

run-mobile: ## Run the Expo mobile proof only
	$(MAKE) -C packages/mobile run

api-types: ## Regenerate the shared TypeScript API contract
	$(MAKE) -C packages/backend api-types

llm-harness: ## Run the reproducible extraction evaluation baseline
	$(MAKE) -C packages/backend llm-harness

load-test: ## Measure the current architecture against stated local targets
	$(MAKE) -C packages/backend load-test

clean: ## Remove build artifacts
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg clean || exit 1; done

distclean: ## Remove build artifacts and installed dependencies
	@for pkg in $(PACKAGES); do $(MAKE) -C $$pkg distclean || exit 1; done

.PHONY: help install build test lint format run run-api run-web run-mobile api-types llm-harness load-test clean distclean
