.DEFAULT_GOAL := help
SHELL := /bin/bash

API_DIR := apps/api
WEB_DIR := apps/web
PY := $(API_DIR)/.venv/bin/python
PIP := $(API_DIR)/.venv/bin/pip

.PHONY: help setup setup-api setup-web api web dev test test-api test-web lint typecheck build migrate sample-data seed clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: setup-api setup-web ## Install all dependencies

setup-api: ## Create the Python virtualenv and install API dependencies
	python3 -m venv $(API_DIR)/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r $(API_DIR)/requirements.txt -r $(API_DIR)/requirements-dev.txt

setup-web: ## Install frontend dependencies
	npm --prefix $(WEB_DIR) ci

api: ## Run the FastAPI service with autoreload (http://127.0.0.1:8000)
	cd $(API_DIR) && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

web: ## Run the Next.js dashboard (http://localhost:3000)
	npm --prefix $(WEB_DIR) run dev

dev: ## Reminder for running both services
	@echo "Run these in two terminals:"
	@echo "  make api    # FastAPI  -> http://127.0.0.1:8000/docs"
	@echo "  make web    # Next.js  -> http://localhost:3000"

test: test-api test-web ## Run all tests

test-api: ## Run API tests with coverage
	cd $(API_DIR) && .venv/bin/python -m pytest --cov=app --cov-report=term-missing

test-web: ## Run frontend tests
	npm --prefix $(WEB_DIR) run test

lint: ## Lint both applications
	cd $(API_DIR) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	npm --prefix $(WEB_DIR) run lint

typecheck: ## Type-check both applications
	cd $(API_DIR) && .venv/bin/mypy app
	npm --prefix $(WEB_DIR) run typecheck

build: ## Production build of the frontend
	npm --prefix $(WEB_DIR) run build

migrate: ## Apply database migrations
	cd $(API_DIR) && .venv/bin/alembic upgrade head

sample-data: ## Regenerate the synthetic sample facility datasets
	cd $(API_DIR) && .venv/bin/python scripts/generate_sample_data.py --hours 168

seed: ## Load the sample facility, dataset and scenarios into a running API
	cd $(API_DIR) && .venv/bin/python scripts/seed_sample.py

clean: ## Remove build and cache artifacts
	rm -rf $(API_DIR)/.pytest_cache $(API_DIR)/.ruff_cache $(API_DIR)/.mypy_cache $(API_DIR)/htmlcov $(API_DIR)/.coverage
	rm -rf $(WEB_DIR)/.next $(WEB_DIR)/coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
