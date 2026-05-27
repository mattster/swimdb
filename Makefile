.PHONY: run dev css css-watch test migrate install

VENV := .venv
PYTHON := $(VENV)/bin/python
TAILWIND := $(VENV)/bin/tailwindcss

# ── Development ────────────────────────────────────────────────────────────────

run:
	$(VENV)/bin/uvicorn app.main:app --reload

dev: css run

# ── CSS (Tailwind v4) ──────────────────────────────────────────────────────────

css:
	$(TAILWIND) build -i static/css/input.css -o static/css/output.css --minify

css-watch:
	$(TAILWIND) build -i static/css/input.css -o static/css/output.css --watch

# ── Tests ──────────────────────────────────────────────────────────────────────

test:
	$(PYTHON) -m pytest tests/

test-fast:
	$(PYTHON) -m pytest tests/ --no-cov -q

# ── Database ───────────────────────────────────────────────────────────────────

migrate:
	$(VENV)/bin/alembic upgrade head

migrate-new:
	@read -p "Migration message: " msg; $(VENV)/bin/alembic revision --autogenerate -m "$$msg"

# ── Setup ──────────────────────────────────────────────────────────────────────

install:
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -e ".[dev]"
	$(VENV)/bin/playwright install chromium
	@echo "Download Tailwind CLI:"
	@echo "  curl -sL https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-macos-arm64 -o $(TAILWIND) && chmod +x $(TAILWIND)"
