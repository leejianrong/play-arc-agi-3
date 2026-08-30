.PHONY: help install run test clean

.DEFAULT_GOAL := help

help:
	@echo "make install  - sync Python dependencies (uv)"
	@echo "make run      - start the app (opens your browser); PORT=xxxx to prefer a port"
	@echo "make test     - run the fast test layer (pytest + node --test), no infra needed"
	@echo "make clean    - remove caches and virtualenv"

install:
	uv sync

run: install
	uv run python main.py

test: install
	uv run pytest
	@if command -v node >/dev/null 2>&1; then \
		node --test tests/unit/*.test.mjs; \
	else \
		echo "node not found, skipping frontend unit tests (tests/unit/*.test.mjs)"; \
	fi

clean:
	rm -rf .venv .pytest_cache
	find . -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
