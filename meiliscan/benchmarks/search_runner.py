"""Search benchmark runner for measuring MeiliSearch performance."""

import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING

from meiliscan.benchmarks.query_generator import QueryGenerator
from meiliscan.models.benchmark import (
    BenchmarkReport,
    IndexBenchmark,
    SearchBenchmarkResult,
    SearchQuery,
)
from meiliscan.models.index import IndexData

if TYPE_CHECKING:
    from meiliscan.collectors.live_instance import LiveInstanceCollector

# Type aliases for progress callbacks
ProgressCallback = Callable[[str, str], Awaitable[None]]  # (index_uid, query_type)
IndexCompleteCallback = Callable[[str], Awaitable[None]]  # (index_uid)


class SearchBenchmarkRunner:
    """Runs search benchmarks against a MeiliSearch instance."""

    def __init__(
        self,
        collector: "LiveInstanceCollector",
        seed: int | None = None,
        queries_per_type: int = 3,
        progress_cb: ProgressCallback | None = None,
        index_complete_cb: IndexCompleteCallback | None = None,
    ):
        """Initialize the benchmark runner.

        Args:
            collector: Connected LiveInstanceCollector
            seed: Optional random seed for reproducibility
            queries_per_type: Number of queries to run per query type
            progress_cb: Optional callback for query progress (index_uid, query_type)
            index_complete_cb: Optional callback when an index benchmark completes (index_uid)
        """
        self._collector = collector
        self._query_generator = QueryGenerator(seed=seed)
        self._queries_per_type = queries_per_type
        self._progress_cb = progress_cb
        self._index_complete_cb = index_complete_cb

    async def _run_single_query(
        self, index_uid: str, query: SearchQuery
    ) -> SearchBenchmarkResult:
        """Run a single search query and measure performance.

        Args:
            index_uid: The index to search
            query: The query to execute

        Returns:
            SearchBenchmarkResult with timing and results
        """
        start_time = time.perf_counter()
        success = True
        error = None
        hits_count = 0
        response_size_bytes = 0
        processing_time_ms = None

        try:
            # Build search parameters
            result = await self._collector.search(
                index_uid=index_uid,
                query=query.query_text,
                filter=query.filter,
                sort=query.sort,
                hits_per_page=20,
                page=1,
            )

            hits_count = result.get("totalHits", len(result.get("hits", [])))

            # Estimate response size
            import json

            response_size_bytes = len(json.dumps(result).encode("utf-8"))

            # Try to get processing time from response (if available)
            processing_time_ms = result.get("processingTimeMs")

        except Exception as e:
            success = False
            error = str(e)

        latency_ms = (time.perf_counter() - start_time) * 1000

        return SearchBenchmarkResult(
            index_uid=index_uid,
            query=query,
            latency_ms=latency_ms,
            processing_time_ms=processing_time_ms,
            hits_count=hits_count,
            response_size_bytes=response_size_bytes,
            success=success,
            error=error,
        )

    async def benchmark_index(
        self, index: IndexData, comprehensive: bool = False
    ) -> IndexBenchmark:
        """Run benchmarks for a single index.

        Args:
            index: The index to benchmark
            comprehensive: If True, run more queries per type

        Returns:
            IndexBenchmark with all results
        """
        queries_per_type = self._queries_per_type if comprehensive else 1
        all_results: list[SearchBenchmarkResult] = []

        # Generate and run queries
        sample_docs = index.sample_documents if index.sample_documents else None

        # Helper to run queries with progress callback
        async def run_queries(query_type: str, generate_fn, *args) -> None:
            if self._progress_cb:
                await self._progress_cb(index.uid, query_type)
            for _ in range(queries_per_type):
                query = generate_fn(*args)
                if query:  # Some generators return None if not applicable
                    result = await self._run_single_query(index.uid, query)
                    all_results.append(result)

        # Baseline queries
        await run_queries(
            "baseline", self._query_generator.generate_baseline_query, index
        )

        # Text queries
        await run_queries("text", self._query_generator.generate_text_query, index)

        # Filtered queries (if applicable)
        await run_queries(
            "filtered",
            self._query_generator.generate_filtered_query,
            index,
            sample_docs,
        )

        # Sorted queries (if applicable)
        await run_queries("sorted", self._query_generator.generate_sorted_query, index)

        # Faceted queries (if applicable)
        await run_queries(
            "faceted", self._query_generator.generate_faceted_query, index
        )

        # Complex queries
        await run_queries(
            "complex",
            self._query_generator.generate_complex_query,
            index,
            sample_docs,
        )

        # Calculate summary metrics by query type
        def avg_latency_for_type(query_type: str) -> float | None:
            type_results = [r for r in all_results if r.query.query_type == query_type]
            if not type_results:
                return None
            return sum(r.latency_ms for r in type_results) / len(type_results)

        return IndexBenchmark(
            index_uid=index.uid,
            document_count=index.document_count,
            baseline_latency_ms=avg_latency_for_type("baseline") or 0.0,
            text_latency_ms=avg_latency_for_type("text"),
            filtered_latency_ms=avg_latency_for_type("filtered"),
            sorted_latency_ms=avg_latency_for_type("sorted"),
            faceted_latency_ms=avg_latency_for_type("faceted"),
            complex_latency_ms=avg_latency_for_type("complex"),
            queries=all_results,
        )

    async def run_baseline(self, indexes: list[IndexData]) -> BenchmarkReport:
        """Run baseline benchmarks (minimal queries per index).

        Args:
            indexes: List of indexes to benchmark

        Returns:
            BenchmarkReport with baseline results
        """
        return await self._run_benchmarks(indexes, comprehensive=False)

    async def run_comprehensive(self, indexes: list[IndexData]) -> BenchmarkReport:
        """Run comprehensive benchmarks (multiple queries per type).

        Args:
            indexes: List of indexes to benchmark

        Returns:
            BenchmarkReport with comprehensive results
        """
        return await self._run_benchmarks(indexes, comprehensive=True)

    async def _run_benchmarks(
        self, indexes: list[IndexData], comprehensive: bool
    ) -> BenchmarkReport:
        """Internal method to run benchmarks.

        Args:
            indexes: List of indexes to benchmark
            comprehensive: Whether to run comprehensive tests

        Returns:
            BenchmarkReport with all results
        """
        start_time = time.perf_counter()
        ran_at = datetime.utcnow()

        # Benchmark each index
        index_benchmarks: list[IndexBenchmark] = []
        for index in indexes:
            benchmark = await self.benchmark_index(index, comprehensive)
            index_benchmarks.append(benchmark)

            # Notify that this index is complete
            if self._index_complete_cb:
                await self._index_complete_cb(index.uid)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Collect all query results for aggregate statistics
        all_results: list[SearchBenchmarkResult] = []
        for idx_bench in index_benchmarks:
            all_results.extend(idx_bench.queries)

        # Calculate aggregate statistics
        all_latencies = [r.latency_ms for r in all_results if r.success]

        if all_latencies:
            avg_overall = sum(all_latencies) / len(all_latencies)
            sorted_latencies = sorted(all_latencies)
            p50 = self._percentile(sorted_latencies, 50)
            p95 = self._percentile(sorted_latencies, 95)
            p99 = self._percentile(sorted_latencies, 99)
            min_latency = min(all_latencies)
            max_latency = max(all_latencies)
        else:
            avg_overall = p50 = p95 = p99 = min_latency = max_latency = 0.0

        # Calculate average baseline latency
        baseline_latencies = [
            r.latency_ms
            for r in all_results
            if r.query.query_type == "baseline" and r.success
        ]
        avg_baseline = (
            sum(baseline_latencies) / len(baseline_latencies)
            if baseline_latencies
            else 0.0
        )

        # Get slowest and fastest queries
        successful_results = [r for r in all_results if r.success]
        slowest = sorted(successful_results, key=lambda r: r.latency_ms, reverse=True)[
            :5
        ]
        fastest = sorted(successful_results, key=lambda r: r.latency_ms)[:5]

        return BenchmarkReport(
            ran_at=ran_at,
            source_url=self._collector.url,
            source_type="instance",
            duration_ms=duration_ms,
            total_queries=len(all_results),
            avg_baseline_ms=avg_baseline,
            avg_overall_ms=avg_overall,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            min_latency_ms=min_latency,
            max_latency_ms=max_latency,
            indexes=index_benchmarks,
            slowest_queries=slowest,
            fastest_queries=fastest,
            comprehensive=comprehensive,
            queries_per_type=self._queries_per_type if comprehensive else 1,
        )

    @staticmethod
    def _percentile(sorted_data: list[float], percentile: int) -> float:
        """Calculate percentile from sorted data.

        Args:
            sorted_data: Sorted list of values
            percentile: Percentile to calculate (0-100)

        Returns:
            The percentile value
        """
        if not sorted_data:
            return 0.0

        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f

        if f == c:
            return sorted_data[f]

        return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)
