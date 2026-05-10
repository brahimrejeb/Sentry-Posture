.PHONY: help install dev run build lint test test-py test-ui clean

help:
	@echo "make install   — sync Python deps (with dev extras) and npm packages"
	@echo "make dev       — run backend + Vite dev server (HMR)"
	@echo "make run       — run production-style backend serving ui/dist"
	@echo "make build     — build the UI into ui/dist"
	@echo "make lint      — ruff backend, eslint ui"
	@echo "make test      — pytest + vitest"
	@echo "make clean     — remove build artefacts and caches"

install:
	uv sync --extra dev
	cd ui && npm install

dev:
	python run.py --dev

run:
	python run.py

build:
	cd ui && npm run build

lint:
	uv run ruff check backend
	cd ui && npm run lint

test: test-py test-ui

test-py:
	uv run pytest

test-ui:
	cd ui && npm test

clean:
	rm -rf ui/dist .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
