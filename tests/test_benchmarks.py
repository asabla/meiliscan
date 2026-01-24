"""Tests for the benchmark modules."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from meiliscan.benchmarks.query_generator import QueryGenerator
from meiliscan.benchmarks.search_runner import SearchBenchmarkRunner
from meiliscan.models.benchmark import (
    BenchmarkReport,
    IndexBenchmark,
    SearchBenchmarkResult,
    SearchQuery,
)
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


# ============================================================================
# Query Generator Tests
# ============================================================================


class TestQueryGenerator:
    """Tests for the QueryGenerator class."""

    @pytest.fixture
    def generator(self) -> QueryGenerator:
        """Create a seeded query generator for reproducible tests."""
        return QueryGenerator(seed=42)

    @pytest.fixture
    def basic_index(self) -> IndexData:
        """Create a basic index with default settings."""
        return IndexData(
            uid="test-index",
            settings=IndexSettings(),
            stats=IndexStats(number_of_documents=100),
        )

    @pytest.fixture
    def configured_index(self) -> IndexData:
        """Create an index with custom settings."""
        return IndexData(
            uid="configured-index",
            settings=IndexSettings(
                searchable_attributes=["title", "description"],
                filterable_attributes=["category", "status", "price"],
                sortable_attributes=["created_at", "price"],
            ),
            stats=IndexStats(number_of_documents=1000),
        )

    def test_generate_baseline_query(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test baseline query generation."""
        query = generator.generate_baseline_query(basic_index)

        assert query.query_type == "baseline"
        assert query.query_text == ""
        assert query.filter is None
        assert query.sort is None
        assert query.facets is None

    def test_generate_text_query(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test text query generation."""
        query = generator.generate_text_query(basic_index, num_words=2)

        assert query.query_type == "text"
        assert len(query.query_text) > 0
        assert " " in query.query_text  # Should have 2 words
        assert query.filter is None

    def test_generate_text_query_uses_common_words(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test that text queries use words from the common words list."""
        query = generator.generate_text_query(basic_index, num_words=1)

        assert query.query_text in QueryGenerator.COMMON_WORDS

    def test_generate_filtered_query_returns_none_without_filterable(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test filtered query returns None when no filterable attributes."""
        query = generator.generate_filtered_query(basic_index)

        assert query is None

    def test_generate_filtered_query_with_filterable(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test filtered query generation with filterable attributes."""
        query = generator.generate_filtered_query(configured_index)

        assert query is not None
        assert query.query_type == "filtered"
        assert query.filter is not None
        assert "EXISTS" in query.filter or "=" in query.filter

    def test_generate_filtered_query_with_sample_documents(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test filtered query uses values from sample documents."""
        sample_docs = [{"category": "electronics", "price": 99.99}]
        query = generator.generate_filtered_query(configured_index, sample_docs)

        assert query is not None
        assert query.filter is not None
        # Should use actual value from sample docs
        assert (
            "electronics" in query.filter
            or "99.99" in query.filter
            or "EXISTS" in query.filter
        )

    def test_generate_filtered_query_with_string_value(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test filtered query with string filter value."""
        # Use fixed seed for predictable attribute selection
        gen = QueryGenerator(seed=0)
        sample_docs = [{"category": "books"}]
        query = gen.generate_filtered_query(configured_index, sample_docs)

        assert query is not None
        # String values should be quoted
        if "books" in (query.filter or ""):
            assert '"books"' in query.filter

    def test_generate_sorted_query_returns_none_without_sortable(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test sorted query returns None when no sortable attributes."""
        query = generator.generate_sorted_query(basic_index)

        assert query is None

    def test_generate_sorted_query_with_sortable(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test sorted query generation with sortable attributes."""
        query = generator.generate_sorted_query(configured_index)

        assert query is not None
        assert query.query_type == "sorted"
        assert query.sort is not None
        assert len(query.sort) == 1
        # Should have format "attr:direction"
        assert ":" in query.sort[0]
        assert query.sort[0].endswith(":asc") or query.sort[0].endswith(":desc")

    def test_generate_faceted_query_returns_none_without_filterable(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test faceted query returns None when no filterable attributes."""
        query = generator.generate_faceted_query(basic_index)

        assert query is None

    def test_generate_faceted_query_with_filterable(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test faceted query generation with filterable attributes."""
        query = generator.generate_faceted_query(configured_index)

        assert query is not None
        assert query.query_type == "faceted"
        assert query.facets is not None
        assert len(query.facets) <= 3  # Max 3 facets

    def test_generate_complex_query(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test complex query combines multiple features."""
        query = generator.generate_complex_query(configured_index)

        assert query.query_type == "complex"
        assert len(query.query_text) > 0  # Has text search
        assert query.filter is not None  # Has filter (since index has filterable)
        assert query.sort is not None  # Has sort (since index has sortable)

    def test_generate_complex_query_basic_index(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test complex query with basic index only has text."""
        query = generator.generate_complex_query(basic_index)

        assert query.query_type == "complex"
        assert len(query.query_text) > 0
        assert query.filter is None  # No filterable attributes
        assert query.sort is None  # No sortable attributes

    def test_generate_all_queries(
        self, generator: QueryGenerator, configured_index: IndexData
    ):
        """Test generating all query types."""
        queries = generator.generate_all_queries(configured_index)

        # Should have all 6 query types since index is fully configured
        assert len(queries) == 6
        query_types = {q.query_type for q in queries}
        assert query_types == {
            "baseline",
            "text",
            "filtered",
            "sorted",
            "faceted",
            "complex",
        }

    def test_generate_all_queries_basic_index(
        self, generator: QueryGenerator, basic_index: IndexData
    ):
        """Test generating queries for basic index filters out None results."""
        queries = generator.generate_all_queries(basic_index)

        # Should only have baseline, text, and complex (filter/sort/facet return None)
        assert len(queries) == 3
        query_types = {q.query_type for q in queries}
        assert query_types == {"baseline", "text", "complex"}

    def test_reproducibility_with_seed(self, configured_index: IndexData):
        """Test that same seed produces same queries."""
        gen1 = QueryGenerator(seed=123)
        gen2 = QueryGenerator(seed=123)

        queries1 = gen1.generate_all_queries(configured_index)
        queries2 = gen2.generate_all_queries(configured_index)

        assert len(queries1) == len(queries2)
        for q1, q2 in zip(queries1, queries2):
            assert q1.query_text == q2.query_text
            assert q1.filter == q2.filter
            assert q1.sort == q2.sort


# ============================================================================
# Search Benchmark Runner Tests
# ============================================================================


class TestSearchBenchmarkRunner:
    """Tests for the SearchBenchmarkRunner class."""

    @pytest.fixture
    def mock_collector(self):
        """Create a mock LiveInstanceCollector."""
        collector = MagicMock()
        collector.url = "http://localhost:7700"
        collector.search = AsyncMock(
            return_value={
                "hits": [{"id": 1}, {"id": 2}],
                "totalHits": 100,
                "processingTimeMs": 5,
            }
        )
        return collector

    @pytest.fixture
    def sample_index(self) -> IndexData:
        """Create a sample index for benchmarking."""
        return IndexData(
            uid="test-index",
            settings=IndexSettings(
                searchable_attributes=["title"],
                filterable_attributes=["category"],
                sortable_attributes=["created_at"],
            ),
            stats=IndexStats(number_of_documents=500),
        )

    @pytest.mark.asyncio
    async def test_run_single_query(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test running a single benchmark query."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42)
        query = SearchQuery(query_type="baseline", query_text="")

        result = await runner._run_single_query(sample_index.uid, query)

        assert result.index_uid == "test-index"
        assert result.query == query
        assert result.latency_ms > 0
        assert result.hits_count == 100
        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_single_query_captures_processing_time(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test that processing time is captured from response."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42)
        query = SearchQuery(query_type="text", query_text="test")

        result = await runner._run_single_query(sample_index.uid, query)

        assert result.processing_time_ms == 5

    @pytest.mark.asyncio
    async def test_run_single_query_handles_error(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test that errors are captured gracefully."""
        mock_collector.search = AsyncMock(side_effect=Exception("Connection failed"))
        runner = SearchBenchmarkRunner(mock_collector, seed=42)
        query = SearchQuery(query_type="baseline", query_text="")

        result = await runner._run_single_query(sample_index.uid, query)

        assert result.success is False
        assert result.error == "Connection failed"
        assert result.hits_count == 0

    @pytest.mark.asyncio
    async def test_benchmark_index(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test benchmarking a single index."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42, queries_per_type=1)

        result = await runner.benchmark_index(sample_index, comprehensive=False)

        assert result.index_uid == "test-index"
        assert result.document_count == 500
        assert result.baseline_latency_ms > 0
        assert len(result.queries) > 0

    @pytest.mark.asyncio
    async def test_benchmark_index_comprehensive(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test comprehensive benchmarking runs more queries."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42, queries_per_type=3)

        result = await runner.benchmark_index(sample_index, comprehensive=True)

        # Should have 3 queries per type
        assert len(result.queries) >= 3  # At least baseline x 3

    @pytest.mark.asyncio
    async def test_run_baseline(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test running baseline benchmarks."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42, queries_per_type=1)

        report = await runner.run_baseline([sample_index])

        assert isinstance(report, BenchmarkReport)
        assert report.source_url == "http://localhost:7700"
        assert report.total_queries > 0
        assert len(report.indexes) == 1
        assert report.comprehensive is False

    @pytest.mark.asyncio
    async def test_run_comprehensive(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test running comprehensive benchmarks."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42, queries_per_type=3)

        report = await runner.run_comprehensive([sample_index])

        assert isinstance(report, BenchmarkReport)
        assert report.comprehensive is True
        assert report.queries_per_type == 3

    @pytest.mark.asyncio
    async def test_benchmark_report_statistics(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test that benchmark report calculates correct statistics."""
        runner = SearchBenchmarkRunner(mock_collector, seed=42, queries_per_type=1)

        report = await runner.run_baseline([sample_index])

        assert report.avg_baseline_ms >= 0
        assert report.avg_overall_ms >= 0
        assert report.p50_latency_ms >= 0
        assert report.p95_latency_ms >= 0
        assert report.p99_latency_ms >= 0
        assert report.min_latency_ms <= report.max_latency_ms

    @pytest.mark.asyncio
    async def test_benchmark_multiple_indexes(self, mock_collector: MagicMock):
        """Test benchmarking multiple indexes."""
        indexes = [
            IndexData(
                uid="index-1",
                settings=IndexSettings(),
                stats=IndexStats(number_of_documents=100),
            ),
            IndexData(
                uid="index-2",
                settings=IndexSettings(),
                stats=IndexStats(number_of_documents=200),
            ),
        ]
        runner = SearchBenchmarkRunner(mock_collector, seed=42, queries_per_type=1)

        report = await runner.run_baseline(indexes)

        assert len(report.indexes) == 2
        assert report.indexes[0].index_uid == "index-1"
        assert report.indexes[1].index_uid == "index-2"

    def test_percentile_calculation(self):
        """Test percentile calculation helper."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        p50 = SearchBenchmarkRunner._percentile(data, 50)
        p95 = SearchBenchmarkRunner._percentile(data, 95)

        assert p50 == pytest.approx(5.5, rel=0.1)
        assert p95 == pytest.approx(9.55, rel=0.1)

    def test_percentile_empty_data(self):
        """Test percentile returns 0 for empty data."""
        assert SearchBenchmarkRunner._percentile([], 50) == 0.0

    def test_percentile_single_value(self):
        """Test percentile with single value."""
        assert SearchBenchmarkRunner._percentile([5.0], 50) == 5.0
        assert SearchBenchmarkRunner._percentile([5.0], 99) == 5.0


# ============================================================================
# Index Benchmark Model Tests
# ============================================================================


class TestIndexBenchmark:
    """Tests for the IndexBenchmark model."""

    def test_avg_latency_ms(self):
        """Test average latency calculation."""
        benchmark = IndexBenchmark(
            index_uid="test",
            document_count=100,
            baseline_latency_ms=10.0,
            queries=[
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="baseline", query_text=""),
                    latency_ms=10.0,
                    hits_count=10,
                    success=True,
                ),
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="text", query_text="test"),
                    latency_ms=20.0,
                    hits_count=5,
                    success=True,
                ),
            ],
        )

        assert benchmark.avg_latency_ms == 15.0

    def test_avg_latency_ms_empty_queries(self):
        """Test average latency with no queries."""
        benchmark = IndexBenchmark(
            index_uid="test",
            document_count=100,
            baseline_latency_ms=0.0,
            queries=[],
        )

        assert benchmark.avg_latency_ms == 0.0

    def test_max_latency_ms(self):
        """Test max latency calculation."""
        benchmark = IndexBenchmark(
            index_uid="test",
            document_count=100,
            baseline_latency_ms=10.0,
            queries=[
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="baseline", query_text=""),
                    latency_ms=10.0,
                    hits_count=10,
                    success=True,
                ),
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="text", query_text="test"),
                    latency_ms=50.0,
                    hits_count=5,
                    success=True,
                ),
            ],
        )

        assert benchmark.max_latency_ms == 50.0

    def test_success_rate(self):
        """Test success rate calculation."""
        benchmark = IndexBenchmark(
            index_uid="test",
            document_count=100,
            baseline_latency_ms=10.0,
            queries=[
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="baseline", query_text=""),
                    latency_ms=10.0,
                    hits_count=10,
                    success=True,
                ),
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="text", query_text="test"),
                    latency_ms=20.0,
                    hits_count=0,
                    success=False,
                    error="Timeout",
                ),
            ],
        )

        assert benchmark.success_rate == 50.0


# ============================================================================
# Benchmark Report Model Tests
# ============================================================================


class TestBenchmarkReport:
    """Tests for the BenchmarkReport model."""

    @pytest.fixture
    def sample_report(self) -> BenchmarkReport:
        """Create a sample benchmark report."""
        return BenchmarkReport(
            ran_at=datetime(2024, 1, 1, 12, 0, 0),
            source_url="http://localhost:7700",
            duration_ms=1000.0,
            total_queries=10,
            avg_baseline_ms=10.0,
            avg_overall_ms=15.0,
            p50_latency_ms=12.0,
            p95_latency_ms=25.0,
            p99_latency_ms=30.0,
            min_latency_ms=5.0,
            max_latency_ms=50.0,
            indexes=[
                IndexBenchmark(
                    index_uid="index-1",
                    document_count=100,
                    baseline_latency_ms=10.0,
                    queries=[],
                ),
                IndexBenchmark(
                    index_uid="index-2",
                    document_count=200,
                    baseline_latency_ms=12.0,
                    queries=[],
                ),
            ],
        )

    def test_get_index_benchmark(self, sample_report: BenchmarkReport):
        """Test getting benchmark by index UID."""
        idx = sample_report.get_index_benchmark("index-1")
        assert idx is not None
        assert idx.index_uid == "index-1"

    def test_get_index_benchmark_not_found(self, sample_report: BenchmarkReport):
        """Test getting benchmark for non-existent index."""
        idx = sample_report.get_index_benchmark("nonexistent")
        assert idx is None

    def test_total_indexes(self, sample_report: BenchmarkReport):
        """Test total indexes count."""
        assert sample_report.total_indexes == 2

    def test_overall_success_rate(self, sample_report: BenchmarkReport):
        """Test overall success rate with no queries."""
        # Empty queries means 100% success rate
        assert sample_report.overall_success_rate == 100.0

    def test_overall_success_rate_with_failures(self):
        """Test overall success rate with some failures."""
        report = BenchmarkReport(
            ran_at=datetime.utcnow(),
            source_url="http://localhost:7700",
            duration_ms=100.0,
            total_queries=4,
            avg_baseline_ms=10.0,
            avg_overall_ms=10.0,
            p50_latency_ms=10.0,
            p95_latency_ms=10.0,
            p99_latency_ms=10.0,
            min_latency_ms=5.0,
            max_latency_ms=15.0,
            indexes=[
                IndexBenchmark(
                    index_uid="test",
                    document_count=100,
                    baseline_latency_ms=10.0,
                    queries=[
                        SearchBenchmarkResult(
                            index_uid="test",
                            query=SearchQuery(query_type="baseline", query_text=""),
                            latency_ms=10.0,
                            hits_count=10,
                            success=True,
                        ),
                        SearchBenchmarkResult(
                            index_uid="test",
                            query=SearchQuery(query_type="text", query_text="test"),
                            latency_ms=10.0,
                            hits_count=0,
                            success=False,
                            error="Error",
                        ),
                    ],
                ),
            ],
        )

        assert report.overall_success_rate == 50.0
