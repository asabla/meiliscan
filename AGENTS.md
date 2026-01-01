# AGENTS.md - MeiliSearch Analyzer

Guidelines for AI coding agents working on this codebase.

## Quick Reference

```bash
# Install dependencies (using uv)
uv sync --all-extras

# Run all tests
uv run pytest

# Run single test file
uv run pytest tests/test_schema_analyzer.py

# Run single test by name
uv run pytest tests/test_schema_analyzer.py::TestSchemaAnalyzer::test_wildcard_searchable_attributes

# Run tests with pattern matching
uv run pytest -k "test_large_documents"

# Run tests with coverage
uv run pytest --cov=meilisearch_analyzer --cov-report=term-missing

# Type checking (not configured, but pydantic handles runtime validation)
# Linting (not configured, follow existing code style)
```

## Project Structure

```
meilisearch_analyzer/
├── analyzers/          # Analysis logic (schema, document, performance, best_practices)
│   └── base.py         # BaseAnalyzer ABC
├── collectors/         # Data collection (live instance, dump parser)
│   └── base.py         # BaseCollector ABC
├── core/               # Orchestration (analyzer, collector, reporter, scorer)
├── exporters/          # Output formats (json, markdown, sarif, agent)
│   └── base.py         # BaseExporter ABC
├── models/             # Pydantic data models (finding, index, report)
├── web/                # FastAPI dashboard
└── cli.py              # Typer CLI entry point
```

## Code Style Guidelines

### Imports

Order imports as: stdlib, third-party, local. Separate groups with blank lines.

```python
"""Module docstring - always include."""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from meilisearch_analyzer.models.finding import Finding, FindingCategory
from meilisearch_analyzer.models.index import IndexData
```

### Type Hints

Always use type hints. Use modern syntax (Python 3.11+):

```python
# Correct
def process(items: list[str], config: dict[str, Any] | None = None) -> list[Finding]:

# Avoid Optional[], use | None instead
# Avoid List[], Dict[] - use lowercase list[], dict[]
```

### Pydantic Models

Use Field with aliases for camelCase JSON compatibility:

```python
class IndexSettings(BaseModel):
    searchable_attributes: list[str] = Field(
        default_factory=lambda: ["*"],
        alias="searchableAttributes"
    )
    
    model_config = {"populate_by_name": True}
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `SchemaAnalyzer`, `FindingSeverity` |
| Functions/methods | snake_case | `analyze_index`, `_check_settings` |
| Constants | UPPER_SNAKE | `DEFAULT_RANKING_RULES`, `CURRENT_STABLE_VERSION` |
| Private methods | _prefix | `_is_id_field`, `_check_pagination` |
| Finding IDs | MEILI-XNNN | `MEILI-S001`, `MEILI-D002`, `MEILI-B004` |

### Finding ID Prefixes

- `S` = Schema (S001-S010)
- `D` = Documents (D001-D008)
- `P` = Performance (P001-P006)
- `B` = Best Practices (B001-B004)

### Docstrings

Use Google-style docstrings:

```python
def analyze(self, index: IndexData) -> list[Finding]:
    """Analyze an index and return findings.

    Args:
        index: The index data to analyze

    Returns:
        List of findings from the analysis
    """
```

### Abstract Base Classes

Analyzers, collectors, and exporters extend ABCs:

```python
class SchemaAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "schema"

    def analyze(self, index: IndexData) -> list[Finding]:
        # Implementation
```

### Creating Findings

Always use the Finding model with all required fields:

```python
Finding(
    id="MEILI-S001",
    category=FindingCategory.SCHEMA,
    severity=FindingSeverity.CRITICAL,
    title="Wildcard searchableAttributes",
    description="Detailed explanation of the issue...",
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

### Async Patterns

Collectors use async/await:

```python
async def connect(self) -> bool:
    self._client = httpx.AsyncClient(...)
    try:
        response = await self._client.get("/health")
        return response.status_code == 200
    except httpx.HTTPError:
        return False
```

### Error Handling

- Use specific exceptions, not bare `except:`
- Collectors return `False` on connection failure, not raise
- CLI displays user-friendly errors via Rich console

```python
try:
    response = await self._client.get("/health")
    response.raise_for_status()
except httpx.HTTPError:
    return False
```

## Testing Patterns

### Test Structure

```python
class TestSchemaAnalyzer:
    """Tests for SchemaAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> SchemaAnalyzer:
        return SchemaAnalyzer()

    @pytest.fixture
    def basic_index(self) -> IndexData:
        return IndexData(
            uid="test_index",
            settings=IndexSettings(...),
            stats=IndexStats(numberOfDocuments=1000, fieldDistribution={...}),
        )

    def test_finding_detection(self, analyzer, basic_index):
        """Test detection of specific finding."""
        findings = analyzer.analyze(basic_index)
        s001_findings = [f for f in findings if f.id == "MEILI-S001"]
        assert len(s001_findings) == 1
        assert s001_findings[0].severity == FindingSeverity.CRITICAL
```

### Async Tests

pytest-asyncio is configured with `asyncio_mode = "auto"`:

```python
async def test_collector_connect(self):
    collector = LiveInstanceCollector(url="http://localhost:7700")
    # respx for mocking HTTP
```

### Test Naming

- `test_<feature>_<finding_id>` for finding tests
- `test_<action>_<condition>` for behavior tests

## CLI Commands

```bash
# Analyze live instance
meilisearch-analyzer analyze --url http://localhost:7700 --api-key key

# Analyze dump file
meilisearch-analyzer analyze --dump ./path/to/dump.dump

# Export formats: json, markdown, sarif, agent
meilisearch-analyzer analyze --url ... --format sarif --output results.sarif

# CI mode (exits non-zero on issues)
meilisearch-analyzer analyze --url ... --ci --fail-on-warnings

# Web dashboard
meilisearch-analyzer serve --url http://localhost:7700 --port 8080
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| pydantic | Data validation and models |
| httpx | Async HTTP client |
| typer | CLI framework |
| rich | Terminal output formatting |
| orjson | Fast JSON serialization |
| pytest-asyncio | Async test support |
| respx | HTTP mocking for tests |
| fastapi | Web dashboard |
