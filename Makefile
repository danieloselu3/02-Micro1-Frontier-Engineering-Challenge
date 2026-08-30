.DEFAULT_GOAL := help
SHELL := /bin/sh
PY := .venv/bin/python
ifeq ($(OS),Windows_NT)
	PY := .venv/Scripts/python.exe
endif

.PHONY: help install up down seed baseline eval eval-replay console test lint clean

help:  ## Show available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Create the virtualenv and install dependencies
	uv venv --python 3.12
	uv pip install --python $(PY) -e ".[dev]"

up:  ## Start Postgres, Redis and MinIO
	docker compose up -d --wait

down:  ## Stop everything and discard volumes
	docker compose down -v

seed:  ## Generate synthetic records, forms and gold labels from a fixed seed
	$(PY) -m data.generator.build --seed 20260830

baseline:  ## Run the single-prompt comparator over the evaluation set
	$(PY) -m eval.harness.run --system baseline

eval:  ## Run the full pipeline over the evaluation set
	$(PY) -m eval.harness.run --system solution

eval-replay:  ## Reproduce both results from committed model responses (no API key)
	$(PY) -m eval.harness.run --system both --replay

console:  ## Serve the reviewer console at http://localhost:8080
	$(PY) -m uvicorn apps.reviewer_console.main:app --port 8080 --reload

test:  ## Run the unit suite
	$(PY) -m pytest -q

lint:  ## Lint and format-check
	$(PY) -m ruff check .

clean:  ## Remove generated artefacts
	rm -rf data/seeds/* eval/cases/* .pytest_cache
