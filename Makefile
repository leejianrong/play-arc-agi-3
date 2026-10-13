.PHONY: help install run run-annotate e2e timeline test lint check hooks download-games clean

.DEFAULT_GOAL := help

help:
	@echo "make install         - sync Python dependencies (uv)"
	@echo "make run             - start the app; prints the URL to open. PORT=xxxx to prefer a port"
	@echo "make run-annotate    - like run, plus the optional speech-to-text extra (faster-whisper) for annotated sessions"
	@echo "make e2e             - drive the real app in headless Chromium with a fake mic (needs games + key; ARGS=\"--only hyp\" / --headed)"
	@echo "make timeline       - render a session as a markdown timeline: FILE=recordings/x.recording.jsonl (default: latest) ARGS=--verify"
	@echo "make test            - run the fast test layer (pytest + node --test), no infra needed"
	@echo "make lint            - run ruff over backend/ main.py scripts/ tests/"
	@echo "make check           - lint + test; what the pre-push hook runs"
	@echo "make hooks           - install the pre-push hook (runs 'make check' before every push)"
	@echo "make download-games  - fetch every real game's source into environment_files/ (idempotent)"
	@echo "make clean           - remove caches and virtualenv"

install:
	uv sync

run: install
	uv run python main.py

# `uv sync` is exact, so it would strip the stt extra; use the extra for both steps here.
run-annotate:
	uv sync --extra stt
	uv run --extra stt python main.py

e2e: install
	uv run --with playwright python scripts/e2e.py $(ARGS)

timeline: install
	uv run python -m backend.timeline $(FILE) $(ARGS)

test: install
	uv run pytest
	@if command -v node >/dev/null 2>&1; then \
		node --test tests/unit/*.test.mjs; \
	else \
		echo "node not found, skipping frontend unit tests (tests/unit/*.test.mjs)"; \
	fi

lint: install
	uv run ruff check backend/ main.py scripts/ tests/

check: lint test

hooks:
	@mkdir -p .git/hooks
	@printf '#!/bin/sh\nmake check\n' > .git/hooks/pre-push
	@chmod +x .git/hooks/pre-push
	@echo "installed .git/hooks/pre-push (runs 'make check' before every push; skip once with git push --no-verify)"

download-games: install
	uv run python -m scripts.download_all_games

clean:
	rm -rf .venv .pytest_cache
	find . -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
