# AGENTS.md - Meiliscan

Guidelines for AI coding agents working on this codebase.

## Quick Reference

```bash
# Setup
make install-dev          # Install all dependencies (uv sync --all-extras)

# Testing
make test                 # Run all tests
make test-file F=tests/test_schema_analyzer.py  # Run single test file
uv run pytest tests/test_schema_analyzer.py::TestSchemaAnalyzer::test_wildcard  # Single test
uv run pytest -k "test_large"  # Pattern matching

# Code quality
make lint                 # Run ruff linter
make format               # Format with ruff

# Development
make serve                # Start web dashboard at http://localhost:8080
make seed-dump            # Create test-dump.dump with sample data
make seed-instance        # Seed MeiliSearch at localhost:7700
```

## Project Structure

```
meiliscan/
├── analyzers/       # Analysis logic (schema, document, performance, best_practices)
├── collectors/      # Data collection (live_instance.py, dump_parser.py)
├── core/            # Orchestration (collector.py, reporter.py, scorer.py)
├── exporters/       # Output formats (json, markdown, sarif, agent)
├── models/          # Pydantic models (finding.py, index.py, report.py)
├── web/             # FastAPI dashboard + templates
└── cli.py           # Typer CLI entry point
```

## Code Style

### Imports
Order: stdlib, third-party, local. Separate with blank lines.

```python
"""Module docstring."""

import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from meiliscan.models.finding import Finding, FindingCategory
```

### Type Hints
Use Python 3.11+ syntax. Prefer `X | None` over `Optional[X]`, lowercase `list[]`/`dict[]`.

```python
def process(items: list[str], config: dict[str, Any] | None = None) -> list[Finding]:
```

### Pydantic Models
Use Field aliases for camelCase JSON compatibility:

```python
class IndexSettings(BaseModel):
    searchable_attributes: list[str] = Field(default_factory=lambda: ["*"], alias="searchableAttributes")
    model_config = {"populate_by_name": True}
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `SchemaAnalyzer`, `FindingSeverity` |
| Functions | snake_case | `analyze_index`, `_check_settings` |
| Constants | UPPER_SNAKE | `DEFAULT_RANKING_RULES` |
| Finding IDs | MEILI-XNNN | `MEILI-S001`, `MEILI-D002` |

### Finding ID Prefixes
- `S` = Schema (S001-S010)
- `D` = Documents (D001-D008)
- `P` = Performance (P001-P006)
- `B` = Best Practices (B001-B004)

### Docstrings
Google-style:

```python
def analyze(self, index: IndexData) -> list[Finding]:
    """Analyze an index and return findings.

    Args:
        index: The index data to analyze

    Returns:
        List of findings from the analysis
    """
```

### Creating Findings

```python
Finding(
    id="MEILI-S001",
    category=FindingCategory.SCHEMA,
    severity=FindingSeverity.CRITICAL,
    title="Wildcard searchableAttributes",
    description="Detailed explanation...",
    impact="What this means for the user",
    index_uid=index.uid,
    current_value=["*"],
    recommended_value=["title", "description"],
    fix=FindingFix(
        type="settings_update",
        endpoint=f"PATCH /indexes/{index.uid}/settings",
        payload={"searchableAttributes": ["title", "description"]},
    ),
    references=["https://www.meilisearch.com/docs/..."],
)
```

### Error Handling
- Use specific exceptions, not bare `except:`
- Collectors return `False` on failure, don't raise
- CLI uses Rich console for user-friendly errors

```python
try:
    response = await self._client.get("/health")
    response.raise_for_status()
except httpx.HTTPError:
    return False
```

## Testing

### Test Structure

```python
class TestSchemaAnalyzer:
    @pytest.fixture
    def analyzer(self) -> SchemaAnalyzer:
        return SchemaAnalyzer()

    @pytest.fixture
    def basic_index(self) -> IndexData:
        return IndexData(uid="test", settings=IndexSettings(), stats=IndexStats())

    def test_wildcard_searchable_attributes(self, analyzer, basic_index):
        findings = analyzer.analyze(basic_index)
        assert any(f.id == "MEILI-S001" for f in findings)
```

### Async Tests
pytest-asyncio configured with `asyncio_mode = "auto"`. Use `respx` for HTTP mocking.

### Test Naming
- `test_<feature>_<finding_id>` for findings
- `test_<action>_<condition>` for behavior

## CLI Commands

```bash
meiliscan analyze --url http://localhost:7700 --api-key key
meiliscan analyze --dump ./dump.dump --format markdown -o report.md
meiliscan analyze --url ... --ci --fail-on-warnings  # CI mode
meiliscan serve --url http://localhost:7700 --port 8080
meiliscan compare old.json new.json -o comparison.md
meiliscan fix-script --input report.json --output fixes.sh
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| pydantic | Data models with validation |
| httpx | Async HTTP client |
| typer/rich | CLI framework and formatting |
| orjson | Fast JSON serialization |
| fastapi/jinja2 | Web dashboard |
| pytest-asyncio/respx | Testing |
