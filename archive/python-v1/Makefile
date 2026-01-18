.PHONY: help install install-dev sync test test-cov test-watch test-file lint format serve clean seed-dump seed-dump-large seed-index seed-instance seed-instance-large seed-instance-index seed-tasks seed-clean

# Default MeiliSearch URL for seeding (can be overridden)
MEILI_URL ?= http://localhost:7700

# Default target
help:
	@echo "Meiliscan - Development Commands"
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
	@echo "Test Data (Dump Files):"
	@echo "  make seed-dump         Create a small dump file (test-dump.dump)"
	@echo "  make seed-dump-large   Create a large dump (~100k docs)"
	@echo "  make seed-index        Seed single index to dump (requires I=<index>)"
	@echo ""
	@echo "Test Data (Live Instance):"
	@echo "  make seed-instance       Seed MeiliSearch instance with default data"
	@echo "  make seed-instance-large Seed instance with large dataset (~100k docs)"
	@echo "  make seed-instance-index Seed single index on instance (requires I=<index>)"
	@echo "  make seed-tasks          Generate tasks on MeiliSearch instance"
	@echo "  make seed-clean          Delete all indexes from MeiliSearch instance"
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
	@echo "  D                 Document count for seed-dump-large/seed-index (default: 100000)"
	@echo "  I                 Index name for seed-index"
	@echo ""
	@echo "Examples:"
	@echo "  make test-file F=tests/test_schema_analyzer.py"
	@echo "  make serve"
	@echo "  make seed-dump"
	@echo "  make seed-dump-large D=500000"
	@echo "  make seed-index I=products D=100000"
	@echo "  make seed-instance"
	@echo "  make seed-instance-large D=500000"
	@echo "  make seed-instance-index I=products D=100000"
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
	uv run meiliscan serve --port 8080

serve-dev:
	uv run uvicorn meiliscan.web.app:app --reload --port 8080

# Testing commands
test:
	uv run pytest

test-cov:
	uv run pytest --cov=meiliscan --cov-report=term-missing --cov-report=html

test-watch:
	uv run pytest-watch

test-file:
	@if [ -z "$(F)" ]; then \
		echo "Usage: make test-file F=tests/test_file.py"; \
		exit 1; \
	fi
	uv run pytest $(F) -v

# Test data commands
# Default document count for large dumps
D ?= 100000

seed-dump:
	@echo "Creating mock dump file..."
	uv run python scripts/seed_data.py dump --output test-dump.dump --size small
	@echo ""
	@echo "Analyze with: meiliscan analyze --dump test-dump.dump"

seed-dump-large:
	@echo "Creating large dump file with $(D) documents..."
	uv run python scripts/seed_data.py dump --output test-dump.dump --documents $(D)
	@echo ""
	@echo "Analyze with: meiliscan analyze --dump test-dump.dump"

seed-index:
	@if [ -z "$(I)" ]; then \
		echo "Usage: make seed-index I=<index> D=<docs>"; \
		echo "Example: make seed-index I=products D=100000"; \
		echo ""; \
		echo "Available indexes:"; \
		echo "  products, users, articles, orders, locations, events,"; \
		echo "  reviews, categories, tags, logs, notifications, inventory,"; \
		echo "  analytics, customers, employees, support_tickets, knowledge_base"; \
		exit 1; \
	fi
	@echo "Creating dump with $(D) documents in index '$(I)'..."
	uv run python scripts/seed_data.py dump --output test-dump.dump --index $(I) --documents $(D)
	@echo ""
	@echo "Analyze with: meiliscan analyze --dump test-dump.dump"

seed-instance:
	@echo "Seeding MeiliSearch instance at $(MEILI_URL)..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_data.py seed --url $(MEILI_URL) --api-key $(MEILI_API_KEY)
else
	uv run python scripts/seed_data.py seed --url $(MEILI_URL)
endif
	@echo ""
	@echo "Analyze with: meiliscan analyze --url $(MEILI_URL)"

seed-instance-large:
	@echo "Seeding MeiliSearch instance at $(MEILI_URL) with $(D) documents..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_data.py seed --url $(MEILI_URL) --api-key $(MEILI_API_KEY) --documents $(D)
else
	uv run python scripts/seed_data.py seed --url $(MEILI_URL) --documents $(D)
endif
	@echo ""
	@echo "Analyze with: meiliscan analyze --url $(MEILI_URL)"

seed-instance-index:
	@if [ -z "$(I)" ]; then \
		echo "Usage: make seed-instance-index I=<index> D=<docs>"; \
		echo "Example: make seed-instance-index I=products D=100000"; \
		echo ""; \
		echo "Available indexes:"; \
		echo "  products, users, articles, orders, locations, events,"; \
		echo "  reviews, categories, tags, logs, notifications, inventory,"; \
		echo "  analytics, customers, employees, support_tickets, knowledge_base"; \
		exit 1; \
	fi
	@echo "Seeding index '$(I)' with $(D) documents at $(MEILI_URL)..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_data.py seed --url $(MEILI_URL) --api-key $(MEILI_API_KEY) --index $(I) --documents $(D)
else
	uv run python scripts/seed_data.py seed --url $(MEILI_URL) --index $(I) --documents $(D)
endif
	@echo ""
	@echo "Analyze with: meiliscan analyze --url $(MEILI_URL)"

seed-clean:
	@echo "Cleaning MeiliSearch instance at $(MEILI_URL)..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_data.py clean --url $(MEILI_URL) --api-key $(MEILI_API_KEY)
else
	uv run python scripts/seed_data.py clean --url $(MEILI_URL)
endif

seed-tasks:
	@echo "Generating tasks on MeiliSearch instance at $(MEILI_URL)..."
ifdef MEILI_API_KEY
	uv run python scripts/seed_tasks.py --url $(MEILI_URL) --api-key $(MEILI_API_KEY)
else
	uv run python scripts/seed_tasks.py --url $(MEILI_URL)
endif
	@echo ""
	@echo "View tasks with: meiliscan tasks --url $(MEILI_URL)"

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
