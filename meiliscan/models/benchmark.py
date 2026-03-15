"""Benchmark models for search performance testing."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """A single search query for benchmarking."""

    query_type: Literal[
        "baseline", "text", "filtered", "sorted", "faceted", "complex"
    ] = Field(..., description="Type of query")
    query_text: str = Field(default="", description="Search query string")
    filter: str | None = Field(default=None, description="Filter expression")
    sort: list[str] | None = Field(default=None, description="Sort expressions")
    facets: list[str] | None = Field(default=None, description="Facet attributes")


class SearchBenchmarkResult(BaseModel):
    """Result from a single search benchmark."""

    index_uid: str = Field(..., description="Index that was searched")
    query: SearchQuery = Field(..., description="Query that was executed")
    latency_ms: float = Field(..., description="Total request latency in milliseconds")
    processing_time_ms: float | None = Field(
        default=None, description="Server processing time from response header"
    )
    hits_count: int = Field(default=0, description="Number of hits returned")
    zero_results: bool = Field(
        default=False, description="Whether the query returned zero results"
    )
    response_size_bytes: int = Field(default=0, description="Response size in bytes")
    success: bool = Field(default=True, description="Whether the query succeeded")
    error: str | None = Field(default=None, description="Error message if failed")


class IndexBenchmark(BaseModel):
    """Benchmark results for a single index."""

    index_uid: str = Field(..., description="Index unique identifier")
    document_count: int = Field(default=0, description="Number of documents in index")

    # Summary latencies (averages if multiple queries per type)
    baseline_latency_ms: float = Field(
        default=0.0, description="Baseline (empty query) latency"
    )
    text_latency_ms: float | None = Field(
        default=None, description="Text search latency"
    )
    filtered_latency_ms: float | None = Field(
        default=None, description="Filtered query latency"
    )
    sorted_latency_ms: float | None = Field(
        default=None, description="Sorted query latency"
    )
    faceted_latency_ms: float | None = Field(
        default=None, description="Faceted query latency"
    )
    complex_latency_ms: float | None = Field(
        default=None, description="Complex query latency"
    )

    # Zero-result tracking
    zero_result_rate: float = Field(
        default=0.0, description="Proportion of queries that returned zero results"
    )

    # All individual query results
    queries: list[SearchBenchmarkResult] = Field(
        default_factory=list, description="Individual query results"
    )

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency across all queries."""
        if not self.queries:
            return 0.0
        return sum(q.latency_ms for q in self.queries) / len(self.queries)

    @property
    def max_latency_ms(self) -> float:
        """Get maximum latency across all queries."""
        if not self.queries:
            return 0.0
        return max(q.latency_ms for q in self.queries)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if not self.queries:
            return 100.0
        successful = sum(1 for q in self.queries if q.success)
        return (successful / len(self.queries)) * 100


class BenchmarkReport(BaseModel):
    """Complete benchmark report for an instance."""

    ran_at: datetime = Field(
        default_factory=datetime.utcnow, description="When benchmark was run"
    )
    source_url: str = Field(..., description="MeiliSearch instance URL")
    source_type: Literal["instance", "dump"] = Field(
        default="instance",
        description="Source type (benchmarks only work on instances)",
    )
    duration_ms: float = Field(default=0.0, description="Total benchmark duration")
    total_queries: int = Field(default=0, description="Total queries executed")

    # Aggregate statistics
    avg_baseline_ms: float = Field(
        default=0.0, description="Average baseline latency across indexes"
    )
    avg_overall_ms: float = Field(
        default=0.0, description="Average latency across all queries"
    )
    p50_latency_ms: float = Field(default=0.0, description="50th percentile latency")
    p95_latency_ms: float = Field(default=0.0, description="95th percentile latency")
    p99_latency_ms: float = Field(default=0.0, description="99th percentile latency")
    min_latency_ms: float = Field(default=0.0, description="Minimum latency")
    max_latency_ms: float = Field(default=0.0, description="Maximum latency")
    stddev_latency_ms: float = Field(
        default=0.0, description="Standard deviation of latency"
    )
    coefficient_of_variation: float = Field(
        default=0.0,
        description="Coefficient of variation (stddev/mean). >0.5 indicates unstable latency",
    )

    # Per-index results
    indexes: list[IndexBenchmark] = Field(
        default_factory=list, description="Per-index benchmark results"
    )

    # Highlighted results
    slowest_queries: list[SearchBenchmarkResult] = Field(
        default_factory=list, description="Top slowest queries"
    )
    fastest_queries: list[SearchBenchmarkResult] = Field(
        default_factory=list, description="Top fastest queries"
    )

    # Configuration used
    comprehensive: bool = Field(
        default=False, description="Whether comprehensive benchmarking was run"
    )
    queries_per_type: int = Field(
        default=1, description="Number of queries run per type"
    )

    def get_index_benchmark(self, index_uid: str) -> IndexBenchmark | None:
        """Get benchmark results for a specific index."""
        for idx in self.indexes:
            if idx.index_uid == index_uid:
                return idx
        return None

    @property
    def total_indexes(self) -> int:
        """Number of indexes benchmarked."""
        return len(self.indexes)

    @property
    def overall_success_rate(self) -> float:
        """Overall success rate across all queries."""
        if not self.indexes:
            return 100.0
        total = sum(len(idx.queries) for idx in self.indexes)
        if total == 0:
            return 100.0
        successful = sum(
            sum(1 for q in idx.queries if q.success) for idx in self.indexes
        )
        return (successful / total) * 100


class FixBenchmark(BaseModel):
    """Before/after benchmark for applying a fix."""

    finding_id: str = Field(..., description="ID of the finding being tested")
    index_uid: str = Field(..., description="Index the fix applies to")
    fix_description: str = Field(..., description="Description of the fix applied")

    # Before state
    before_benchmark: IndexBenchmark = Field(
        ..., description="Benchmark results before applying fix"
    )
    before_settings: dict[str, Any] = Field(
        default_factory=dict, description="Settings before fix"
    )

    # After state (None if fix not applied)
    after_benchmark: IndexBenchmark | None = Field(
        default=None, description="Benchmark results after applying fix"
    )
    after_settings: dict[str, Any] | None = Field(
        default=None, description="Settings after fix"
    )

    # Execution details
    applied: bool = Field(default=False, description="Whether fix was actually applied")
    reverted: bool = Field(
        default=False, description="Whether settings were reverted after"
    )
    waited_for_indexing: bool = Field(
        default=False, description="Whether we waited for re-indexing"
    )
    indexing_duration_ms: float | None = Field(
        default=None, description="Time spent waiting for indexing"
    )

    # Results
    improvement_percent: float | None = Field(
        default=None, description="Latency improvement percentage (negative = worse)"
    )
    error: str | None = Field(default=None, description="Error if something went wrong")

    @property
    def latency_change_ms(self) -> float | None:
        """Calculate latency change in ms (negative = improvement)."""
        if not self.after_benchmark:
            return None
        return (
            self.after_benchmark.avg_latency_ms - self.before_benchmark.avg_latency_ms
        )

    @property
    def improved(self) -> bool:
        """Whether the fix improved performance."""
        if self.improvement_percent is None:
            return False
        return self.improvement_percent > 0
