.PHONY: help install install-dev sync test test-cov test-watch test-file lint format serve clean seed-dump seed-instance seed-clean

# Default MeiliSearch URL for seeding (can be overridden)
MEILI_URL ?= http://localhost:7700

# Default target
help:
	@echo "MeiliSearch Analyzer - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install dependencies"
	@echo "  make install-dev  Install all dependencies including dev tools"
	@echo "  make sync         Sync dependencies with lockfile"
	@echo ""
	@echo "Development:"
	@echo "  make serve        Start web dashboard on http://localhost:8080"
	@echo "  make serve-dev    Start web dashboard with auto-reload"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests"
	@echo "  make test-cov     Run tests with coverage report"
	@echo "  make test-watch   Run tests in watch mode (requires pytest-watch)"
	@echo "  make test-file F=<file>  Run specific test file"
	@echo ""
	@echo "Test Data:"
	@echo "  make seed-dump    Create a mock dump file (test-dump.dump)"
	@echo "  make seed-instance  Seed MeiliSearch instance with test data"
	@echo "  make seed-clean   Delete all indexes from MeiliSearch instance"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         Run linter (ruff)"
	@echo "  make format       Format code (ruff)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean        Remove build artifacts and cache"
	@echo ""
	@echo "Variables:"
	@echo "  MEILI_URL         MeiliSearch URL (default: $(MEILI_URL))"
	@echo "  MEILI_API_KEY     MeiliSearch API key (optional)"
	@echo ""
	@echo "Examples:"
	@echo "  make test-file F=tests/test_schema_analyzer.py"
	@echo "  make serve"
	@echo "  make seed-instance"
	@echo "  make seed-instance MEILI_URL=http://localhost:7700"
	@echo "  make seed-instance MEILI_URL=http://localhost:7700 MEILI_API_KEY=my-key"

# Setup commands
install:
	uv sync

install-dev:
	uv sync --all-extras

sync:
	uv sync --all-extras

# Development commands
serve:
	uv run meilisearch-analyzer serve --port 8080

serve-dev:
	uv run uvicorn meilisearch_analyzer.web.app:app --reload --port 8080

# Testing commands
test:
	uv run pytest

test-cov:
	uv run pytest --cov=meilisearch_analyzer --cov-report=term-missing --cov-report=html

test-watch:
	uv run pytest-watch

test-file:
	@if [ -z "$(F)" ]; then \
		echo "Usage: make test-file F=tests/test_file.py"; \
		exit 1; \
	fi
	uv run pytest $(F) -v

# Test data commands
seed-dump:
	@echo "Creating mock dump file..."
	uv run python scripts/seed_data.py dump --output test-dump.dump
	@echo ""
	@echo "Analyze with: meilisearch-analyzer analyze --dump test-dump.dump"

seed-instance:
	@echo "Seeding MeiliSearch instance at $(MEILI_URL)..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_data.py seed --url $(MEILI_URL) --api-key $(MEILI_API_KEY)
else
	uv run python scripts/seed_data.py seed --url $(MEILI_URL)
endif
	@echo ""
	@echo "Analyze with: meilisearch-analyzer analyze --url $(MEILI_URL)"

seed-clean:
	@echo "Cleaning MeiliSearch instance at $(MEILI_URL)..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_data.py clean --url $(MEILI_URL) --api-key $(MEILI_API_KEY)
else
	uv run python scripts/seed_data.py clean --url $(MEILI_URL)
endif

# Code quality commands
lint:
	uv run ruff check .

format:
	uv run ruff format .

# Utility commands
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .ruff_cache/
	rm -rf test-dump.dump
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
