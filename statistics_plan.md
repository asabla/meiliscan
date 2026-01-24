# Statistics Widget & Benchmarking Plan

## Overview

Replace the penalty-based "Health Score" with a **Statistics Dashboard** that provides actionable insights about:

1. **Performance potential** - estimated gains from implementing fixes
2. **Configuration coverage** - what's configured vs defaults
3. **Resource usage** - database/index sizes, document counts
4. **Response times** - captured during collection phase
5. **Benchmarking** (live instances only) - search latency measurements

## Key Decisions

1. **Remove health score entirely** - Replace with statistics widget
2. **Implement apply-fix benchmarking** with safeguards (confirmation, backups, revert capability)
3. **Benchmark results**: Include in report when run + separate downloadable export

---

## Phase 1: Core Models & Infrastructure

### 1.1 New Models (`meiliscan/models/statistics.py`)

```python
# Timing from data collection
class CollectionTiming(BaseModel):
    connect_ms: float
    version_ms: float
    stats_ms: float
    indexes_list_ms: float
    per_index_avg_ms: float
    total_ms: float

# Per-index statistics
class IndexStatistics(BaseModel):
    uid: str
    document_count: int
    field_count: int
    size_bytes: int | None

    # Configuration coverage (booleans)
    has_custom_searchable: bool
    has_custom_filterable: bool
    has_custom_sortable: bool
    has_custom_ranking: bool
    has_stop_words: bool
    has_synonyms: bool
    has_typo_config: bool
    configuration_coverage: int  # 0-100%

    # Issue counts
    critical_count: int
    warning_count: int
    suggestion_count: int

# Performance improvement opportunities
class PerformanceOpportunity(BaseModel):
    id: str  # Link to finding ID
    category: str
    title: str
    description: str
    estimated_impact: Literal["high", "medium", "low"]
    affected_indexes: list[str]
    estimated_improvement: str  # Human readable

# Overall statistics
class InstanceStatistics(BaseModel):
    # Resources
    total_indexes: int
    total_documents: int
    total_fields: int
    database_size_bytes: int | None
    used_size_bytes: int | None
    fragmentation_percent: float | None

    # Configuration coverage
    indexes_with_custom_searchable: int
    indexes_with_custom_filterable: int
    indexes_with_custom_sortable: int
    indexes_with_custom_ranking: int
    overall_coverage_percent: int

    # Collection timing
    collection_timing: CollectionTiming | None

    # Breakdowns
    index_statistics: list[IndexStatistics]
    performance_opportunities: list[PerformanceOpportunity]
```

### 1.2 Benchmark Models (`meiliscan/models/benchmark.py`)

```python
class SearchQuery(BaseModel):
    """A single search query for benchmarking."""
    query_type: str  # "baseline", "text", "filtered", "sorted", "faceted", "complex"
    query_text: str
    filter: str | None
    sort: list[str] | None
    facets: list[str] | None

class SearchBenchmarkResult(BaseModel):
    """Result from a single search benchmark."""
    index_uid: str
    query: SearchQuery
    latency_ms: float
    processing_time_ms: float | None  # From X-Meili-Process-Time header
    hits_count: int
    response_size_bytes: int
    success: bool
    error: str | None

class IndexBenchmark(BaseModel):
    """Benchmark results for a single index."""
    index_uid: str
    baseline_latency_ms: float
    filtered_latency_ms: float | None
    sorted_latency_ms: float | None
    faceted_latency_ms: float | None
    complex_latency_ms: float | None
    queries: list[SearchBenchmarkResult]

class BenchmarkReport(BaseModel):
    """Complete benchmark report."""
    ran_at: datetime
    source_url: str
    duration_ms: float
    total_queries: int

    # Aggregate stats
    avg_baseline_ms: float
    avg_overall_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float

    # Per-index results
    indexes: list[IndexBenchmark]

    # Slowest queries
    slowest_queries: list[SearchBenchmarkResult]

class FixBenchmark(BaseModel):
    """Before/after benchmark for a fix."""
    finding_id: str
    index_uid: str
    fix_description: str

    # Before measurements
    before_benchmark: IndexBenchmark
    before_settings: dict[str, Any]

    # After measurements (None if not applied)
    after_benchmark: IndexBenchmark | None
    after_settings: dict[str, Any] | None

    # Results
    applied: bool
    reverted: bool
    improvement_percent: float | None
    error: str | None
```

---

## Phase 2: Timing in Collector

Modify `meiliscan/collectors/live_instance.py`:

```python
class LiveInstanceCollector:
    def __init__(self, ...):
        ...
        self._timing = CollectionTiming(...)  # Track timing

    async def connect(self, ...):
        start = time.perf_counter()
        # ... existing code ...
        self._timing.connect_ms = (time.perf_counter() - start) * 1000

    @property
    def timing(self) -> CollectionTiming:
        return self._timing
```

---

## Phase 3: Statistics Calculator

New `meiliscan/core/statistics.py`:

- `calculate_statistics(report: AnalysisReport) -> InstanceStatistics`
- `calculate_index_statistics(index: IndexAnalysis) -> IndexStatistics`
- `calculate_configuration_coverage(settings: IndexSettings) -> int`
- `identify_performance_opportunities(findings: list[Finding]) -> list[PerformanceOpportunity]`

---

## Phase 4: Benchmarking Module

New `meiliscan/benchmarks/` package:

```
benchmarks/
├── __init__.py
├── search_runner.py      # Run search benchmarks
├── query_generator.py    # Generate test queries
├── fix_benchmark.py      # Before/after with fix application
└── reporter.py           # Format benchmark results
```

### `search_runner.py`

```python
class SearchBenchmarkRunner:
    async def run_baseline(self, collector, indexes) -> BenchmarkReport
    async def run_comprehensive(self, collector, indexes) -> BenchmarkReport
```

### `fix_benchmark.py`

```python
class FixBenchmarkRunner:
    """Run before/after benchmarks by applying a fix."""

    async def benchmark_fix(
        self,
        collector: LiveInstanceCollector,
        finding: Finding,
        dry_run: bool = True,
    ) -> FixBenchmark:
        """
        1. Run baseline benchmark
        2. If not dry_run: Apply fix
        3. Wait for indexing
        4. Run after benchmark
        5. If not dry_run and revert requested: Revert settings
        """
```

### Safeguards for fix application

- Require explicit `--apply-fixes` flag
- Require confirmation prompt (unless `--yes`)
- Backup original settings before applying
- Provide `--revert` command to restore settings
- Timeout protection (don't wait forever for indexing)
- Only apply settings changes (never delete data)

---

## Phase 5: Report Model Changes

Update `meiliscan/models/report.py`:

```python
class AnalysisReport(BaseModel):
    # ... existing fields ...

    # Remove: summary.health_score

    # Add:
    statistics: InstanceStatistics | None = None
    benchmark: BenchmarkReport | None = None
```

Remove from `AnalysisSummary`:

- `health_score` field

Delete `meiliscan/core/scorer.py` entirely.

---

## Phase 6: Web Dashboard UI

Replace score card in `dashboard.html` with a tabbed statistics widget:

### Tabs

1. **Overview Tab**
   - Total indexes, documents, database size
   - Configuration coverage gauge
   - Collection timing

2. **Performance Tab**
   - List of performance opportunities grouped by impact
   - Affected indexes for each opportunity
   - Estimated improvements

3. **Indexes Tab**
   - Per-index breakdown table
   - Columns: Index, Docs, Fields, Config %, Issues
   - Sortable

4. **Benchmark Tab** (live instances only)
   - Run benchmark button
   - Results table when available
   - Export option

---

## Phase 7: API Endpoints

New routes in `routes.py`:

```python
@router.get("/api/statistics")
async def get_statistics() -> InstanceStatistics:
    """Get computed statistics for the current report."""

@router.post("/api/benchmark")
async def run_benchmark(comprehensive: bool = False) -> BenchmarkReport:
    """Run benchmarks against the live instance."""

@router.get("/api/benchmark")
async def get_benchmark() -> BenchmarkReport | None:
    """Get existing benchmark results from the report."""

@router.get("/api/benchmark/export")
async def export_benchmark(format: str = "json"):
    """Download benchmark results separately."""

@router.post("/api/benchmark/fix/{finding_id}")
async def benchmark_fix(
    finding_id: str,
    apply: bool = False,
    revert_after: bool = True,
) -> FixBenchmark:
    """Benchmark a specific fix (optionally applying it)."""
```

---

## Phase 8: CLI Updates ✅ COMPLETED

### New benchmark command

```python
@app.command()
def benchmark(
    url: str,
    api_key: str | None = None,
    comprehensive: bool = False,
    output: Path | None = None,
    format: str = "json",
    indexes: str | None = None,  # Filter by index UIDs
):
    """Run search benchmarks against a live instance."""
```

**Implemented in commit `197bf05`:**
- `meiliscan benchmark --url <url>` - Basic benchmark
- `--comprehensive` / `-c` - Run multiple queries per type
- `--output` / `-o` - Save results to file
- `--format` / `-f` - Output as json or markdown
- `--indexes` / `-i` - Filter by comma-separated index UIDs
- Rich panel display with latency statistics
- Per-index results table
- Slowest queries summary

### Updated CLI output format

```
╭─────────────────────── Instance Statistics ───────────────────────╮
│                                                                   │
│  Resources                                                        │
│  ─────────────────────────────────────────────────────────────── │
│  Indexes: 5          Documents: 1,234,567       Size: 450.2 MB   │
│  Fields: 47          Fragmentation: 12%                          │
│                                                                   │
│  Configuration Coverage: 45%                                      │
│  ██████████████░░░░░░░░░░░░░░░░                                  │
│  • 2/5 indexes have custom searchableAttributes                  │
│  • 3/5 indexes have custom filterableAttributes                  │
│  • 1/5 indexes have custom ranking rules                         │
│                                                                   │
│  Collection Time: 1,234ms                                         │
│                                                                   │
╰───────────────────────────────────────────────────────────────────╯

╭─────────────────── Performance Opportunities ─────────────────────╮
│                                                                   │
│  HIGH IMPACT                                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Configure searchableAttributes                              │ │
│  │ Affects: products, articles, users                          │ │
│  │ Potential: Reduce index size by ~40%, faster indexing       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  MEDIUM IMPACT                                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Add stop words for English content                          │ │
│  │ Affects: articles, blog_posts                               │ │
│  │ Potential: ~15% smaller index, better relevance             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
╰───────────────────────────────────────────────────────────────────╯
```

---

## Files to Create/Modify

| Action | File                                       | Description                                    |
| ------ | ------------------------------------------ | ---------------------------------------------- |
| Create | `meiliscan/models/statistics.py`           | Statistics data models                         |
| Create | `meiliscan/models/benchmark.py`            | Benchmark data models                          |
| Create | `meiliscan/core/statistics.py`             | Statistics calculator                          |
| Create | `meiliscan/benchmarks/__init__.py`         | Benchmark package                              |
| Create | `meiliscan/benchmarks/search_runner.py`    | Search benchmark runner                        |
| Create | `meiliscan/benchmarks/query_generator.py`  | Test query generation                          |
| Create | `meiliscan/benchmarks/fix_benchmark.py`    | Fix application benchmarking                   |
| Modify | `meiliscan/collectors/live_instance.py`    | Add timing capture                             |
| Modify | `meiliscan/models/report.py`               | Add statistics/benchmark, remove health_score  |
| Delete | `meiliscan/core/scorer.py`                 | Remove health scorer                           |
| Modify | `meiliscan/core/reporter.py`               | Use statistics instead of scorer               |
| Modify | `meiliscan/web/routes.py`                  | New API endpoints                              |
| Modify | `meiliscan/web/templates/dashboard.html`   | New statistics widget                          |
| Modify | `meiliscan/cli.py`                         | New benchmark command, updated output          |
| Modify | `meiliscan/exporters/*.py`                 | Update export formats                          |
| Create | Tests for all new modules                  |                                                |

---

## Estimated Effort

| Phase                          | Effort    |
| ------------------------------ | --------- |
| Phase 1: Core Models           | ~2 hours  |
| Phase 2: Timing in Collector   | ~1 hour   |
| Phase 3: Statistics Calculator | ~2 hours  |
| Phase 4: Benchmarking Module   | ~4 hours  |
| Phase 5: Report Model Changes  | ~1 hour   |
| Phase 6: Web Dashboard UI      | ~3 hours  |
| Phase 7: API Endpoints         | ~2 hours  |
| Phase 8: CLI Updates           | ~2 hours  |
| Tests                          | ~3 hours  |
| **Total**                      | **~20 hours** |
