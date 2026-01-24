"""Tests for the benchmark modules."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from meiliscan.benchmarks.fix_benchmark import FixBenchmarkRunner
from meiliscan.benchmarks.query_generator import QueryGenerator
from meiliscan.benchmarks.search_runner import SearchBenchmarkRunner
from meiliscan.models.benchmark import (
    BenchmarkReport,
    FixBenchmark,
    IndexBenchmark,
    SearchBenchmarkResult,
    SearchQuery,
)
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
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


# ============================================================================
# FixBenchmark Model Tests
# ============================================================================


class TestFixBenchmark:
    """Tests for the FixBenchmark model."""

    @pytest.fixture
    def before_benchmark(self) -> IndexBenchmark:
        """Create a before benchmark."""
        return IndexBenchmark(
            index_uid="test",
            document_count=100,
            baseline_latency_ms=20.0,
            queries=[
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="baseline", query_text=""),
                    latency_ms=20.0,
                    hits_count=10,
                    success=True,
                ),
            ],
        )

    @pytest.fixture
    def after_benchmark(self) -> IndexBenchmark:
        """Create an after benchmark with improved latency."""
        return IndexBenchmark(
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
            ],
        )

    def test_fix_benchmark_creation(self, before_benchmark: IndexBenchmark):
        """Test creating a FixBenchmark."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Configure searchable attributes",
            before_benchmark=before_benchmark,
            before_settings={"searchableAttributes": ["*"]},
        )

        assert fix.finding_id == "MEILI-S001"
        assert fix.index_uid == "test"
        assert fix.applied is False
        assert fix.reverted is False
        assert fix.after_benchmark is None
        assert fix.improvement_percent is None

    def test_fix_benchmark_with_after(
        self, before_benchmark: IndexBenchmark, after_benchmark: IndexBenchmark
    ):
        """Test FixBenchmark with after benchmark."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Configure searchable attributes",
            before_benchmark=before_benchmark,
            before_settings={"searchableAttributes": ["*"]},
            after_benchmark=after_benchmark,
            after_settings={"searchableAttributes": ["title", "description"]},
            applied=True,
            reverted=True,
            improvement_percent=50.0,
        )

        assert fix.applied is True
        assert fix.reverted is True
        assert fix.after_benchmark is not None
        assert fix.improvement_percent == 50.0

    def test_latency_change_ms_with_improvement(
        self, before_benchmark: IndexBenchmark, after_benchmark: IndexBenchmark
    ):
        """Test latency change calculation with improvement."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
            after_benchmark=after_benchmark,
        )

        # After (10ms) - Before (20ms) = -10ms (improvement)
        assert fix.latency_change_ms == -10.0

    def test_latency_change_ms_with_regression(self, before_benchmark: IndexBenchmark):
        """Test latency change calculation with regression."""
        worse_after = IndexBenchmark(
            index_uid="test",
            document_count=100,
            baseline_latency_ms=30.0,
            queries=[
                SearchBenchmarkResult(
                    index_uid="test",
                    query=SearchQuery(query_type="baseline", query_text=""),
                    latency_ms=30.0,
                    hits_count=10,
                    success=True,
                ),
            ],
        )

        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
            after_benchmark=worse_after,
        )

        # After (30ms) - Before (20ms) = 10ms (regression)
        assert fix.latency_change_ms == 10.0

    def test_latency_change_ms_none_without_after(
        self, before_benchmark: IndexBenchmark
    ):
        """Test latency change is None when no after benchmark."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
        )

        assert fix.latency_change_ms is None

    def test_improved_true_with_positive_improvement(
        self, before_benchmark: IndexBenchmark, after_benchmark: IndexBenchmark
    ):
        """Test improved property returns True for positive improvement."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
            after_benchmark=after_benchmark,
            improvement_percent=50.0,
        )

        assert fix.improved is True

    def test_improved_false_with_negative_improvement(
        self, before_benchmark: IndexBenchmark
    ):
        """Test improved property returns False for negative improvement."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
            improvement_percent=-20.0,
        )

        assert fix.improved is False

    def test_improved_false_without_improvement(self, before_benchmark: IndexBenchmark):
        """Test improved property returns False when improvement_percent is None."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
        )

        assert fix.improved is False

    def test_fix_benchmark_with_error(self, before_benchmark: IndexBenchmark):
        """Test FixBenchmark with error."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
            error="Failed to apply fix: Connection refused",
        )

        assert fix.error == "Failed to apply fix: Connection refused"
        assert fix.applied is False

    def test_fix_benchmark_with_indexing_time(
        self, before_benchmark: IndexBenchmark, after_benchmark: IndexBenchmark
    ):
        """Test FixBenchmark tracks indexing duration."""
        fix = FixBenchmark(
            finding_id="MEILI-S001",
            index_uid="test",
            fix_description="Test fix",
            before_benchmark=before_benchmark,
            after_benchmark=after_benchmark,
            applied=True,
            waited_for_indexing=True,
            indexing_duration_ms=5000.0,
        )

        assert fix.waited_for_indexing is True
        assert fix.indexing_duration_ms == 5000.0


# ============================================================================
# FixBenchmarkRunner Tests
# ============================================================================


class TestFixBenchmarkRunner:
    """Tests for the FixBenchmarkRunner class."""

    @pytest.fixture
    def mock_collector(self) -> MagicMock:
        """Create a mock LiveInstanceCollector."""
        collector = MagicMock()
        collector.url = "http://localhost:7700"
        collector._client = MagicMock()
        collector.search = AsyncMock(
            return_value={
                "hits": [{"id": 1}],
                "totalHits": 10,
                "processingTimeMs": 5,
            }
        )
        collector.get_index_settings = AsyncMock(
            return_value={"searchableAttributes": ["*"], "filterableAttributes": []}
        )
        collector.get_task = AsyncMock(
            return_value=MagicMock(status=MagicMock(value="succeeded"), error=None)
        )
        return collector

    @pytest.fixture
    def sample_index(self) -> IndexData:
        """Create a sample index for testing."""
        return IndexData(
            uid="test-index",
            settings=IndexSettings(
                searchable_attributes=["title", "description"],
                filterable_attributes=["category"],
                sortable_attributes=["created_at"],
            ),
            stats=IndexStats(number_of_documents=100),
        )

    @pytest.fixture
    def sample_finding(self) -> Finding:
        """Create a sample finding with a fix."""
        return Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Wildcard searchableAttributes",
            description="All fields are searchable",
            impact="Performance degradation",
            index_uid="test-index",
            current_value=["*"],
            recommended_value=["title", "description"],
            fix=FindingFix(
                type="settings_update",
                endpoint="PATCH /indexes/test-index/settings",
                payload={"searchableAttributes": ["title", "description"]},
            ),
        )

    @pytest.fixture
    def finding_without_fix(self) -> Finding:
        """Create a finding without a fix."""
        return Finding(
            id="MEILI-B003",
            category=FindingCategory.BEST_PRACTICES,
            severity=FindingSeverity.INFO,
            title="Missing embedders config",
            description="No AI/vector search configuration",
            impact="Missing vector search capability",
            index_uid=None,
        )

    def test_runner_initialization(self, mock_collector: MagicMock):
        """Test FixBenchmarkRunner initialization."""
        runner = FixBenchmarkRunner(mock_collector, seed=42)

        assert runner._collector == mock_collector
        assert runner._benchmark_runner is not None
        # SearchBenchmarkRunner is created with queries_per_type=3 for fix benchmarks
        assert runner._benchmark_runner._queries_per_type == 3

    def test_runner_default_constants(self, mock_collector: MagicMock):
        """Test default constants are set correctly."""
        runner = FixBenchmarkRunner(mock_collector)

        assert runner.MAX_INDEXING_WAIT == 300
        assert runner.INDEXING_POLL_INTERVAL == 2

    @pytest.mark.asyncio
    async def test_benchmark_fix_dry_run(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        sample_finding: Finding,
    ):
        """Test dry run benchmark (apply=False)."""
        runner = FixBenchmarkRunner(mock_collector, seed=42)

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=sample_finding,
            apply=False,
        )

        assert result.finding_id == "MEILI-S001"
        assert result.index_uid == "test-index"
        assert result.applied is False
        assert result.reverted is False
        assert result.after_benchmark is None
        assert result.before_benchmark is not None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_benchmark_fix_without_fix_returns_error(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        finding_without_fix: Finding,
    ):
        """Test benchmark with finding that has no fix defined."""
        runner = FixBenchmarkRunner(mock_collector, seed=42)

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=finding_without_fix,
            apply=True,
        )

        assert result.applied is False
        assert result.error == "Finding has no fix defined"

    @pytest.mark.asyncio
    async def test_benchmark_fix_apply_success(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        sample_finding: Finding,
    ):
        """Test successful fix application and benchmark."""
        # Mock PATCH response for applying fix
        mock_patch_response = MagicMock()
        mock_patch_response.json.return_value = {"taskUid": 123}
        mock_patch_response.raise_for_status = MagicMock()
        mock_collector._client.patch = AsyncMock(return_value=mock_patch_response)

        # Mock PUT response for reverting settings
        mock_put_response = MagicMock()
        mock_put_response.json.return_value = {"taskUid": 124}
        mock_put_response.raise_for_status = MagicMock()
        mock_collector._client.put = AsyncMock(return_value=mock_put_response)

        # Mock GET response for indexing status
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"isIndexing": False}
        mock_get_response.raise_for_status = MagicMock()
        mock_collector._client.get = AsyncMock(return_value=mock_get_response)

        runner = FixBenchmarkRunner(mock_collector, seed=42)

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=sample_finding,
            apply=True,
            revert_after=True,
        )

        assert result.applied is True
        assert result.reverted is True
        assert result.after_benchmark is not None
        assert result.waited_for_indexing is True
        assert result.error is None
        # Verify the PATCH was called with correct payload
        mock_collector._client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_benchmark_fix_apply_without_revert(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        sample_finding: Finding,
    ):
        """Test fix application without reverting."""
        mock_patch_response = MagicMock()
        mock_patch_response.json.return_value = {"taskUid": 123}
        mock_patch_response.raise_for_status = MagicMock()
        mock_collector._client.patch = AsyncMock(return_value=mock_patch_response)

        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"isIndexing": False}
        mock_get_response.raise_for_status = MagicMock()
        mock_collector._client.get = AsyncMock(return_value=mock_get_response)

        runner = FixBenchmarkRunner(mock_collector, seed=42)

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=sample_finding,
            apply=True,
            revert_after=False,
        )

        assert result.applied is True
        assert result.reverted is False
        # PUT should not be called when revert_after=False
        mock_collector._client.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_benchmark_fix_apply_failure(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        sample_finding: Finding,
    ):
        """Test fix application failure."""
        mock_collector._client.patch = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        runner = FixBenchmarkRunner(mock_collector, seed=42)

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=sample_finding,
            apply=True,
        )

        assert result.applied is False
        assert "Failed to apply fix" in result.error

    @pytest.mark.asyncio
    async def test_wait_for_task_success(self, mock_collector: MagicMock):
        """Test waiting for task completion."""
        runner = FixBenchmarkRunner(mock_collector)

        # Should not raise
        await runner._wait_for_task(123, timeout=5.0)

        mock_collector.get_task.assert_called_with(123)

    @pytest.mark.asyncio
    async def test_wait_for_task_failure(self, mock_collector: MagicMock):
        """Test waiting for a failed task."""
        mock_collector.get_task = AsyncMock(
            return_value=MagicMock(
                status=MagicMock(value="failed"),
                error=MagicMock(message="Index not found"),
            )
        )

        runner = FixBenchmarkRunner(mock_collector)

        with pytest.raises(Exception, match="Task failed"):
            await runner._wait_for_task(123, timeout=5.0)

    @pytest.mark.asyncio
    async def test_wait_for_task_not_found(self, mock_collector: MagicMock):
        """Test waiting for non-existent task."""
        mock_collector.get_task = AsyncMock(return_value=None)

        runner = FixBenchmarkRunner(mock_collector)

        with pytest.raises(Exception, match="Task 123 not found"):
            await runner._wait_for_task(123, timeout=5.0)

    @pytest.mark.asyncio
    async def test_wait_for_indexing_completes(self, mock_collector: MagicMock):
        """Test waiting for indexing to complete."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"isIndexing": False}
        mock_response.raise_for_status = MagicMock()
        mock_collector._client.get = AsyncMock(return_value=mock_response)

        runner = FixBenchmarkRunner(mock_collector)

        # Should complete without raising
        await runner._wait_for_indexing("test-index")

    @pytest.mark.asyncio
    async def test_wait_for_indexing_polls(self, mock_collector: MagicMock):
        """Test indexing polling when initially indexing."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            # Return isIndexing=True twice, then False
            mock_response.json.return_value = {"isIndexing": call_count < 3}
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_collector._client.get = mock_get

        runner = FixBenchmarkRunner(mock_collector)
        # Set a short poll interval for testing
        runner.INDEXING_POLL_INTERVAL = 0.01

        await runner._wait_for_indexing("test-index")

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_apply_fix_calls_patch(
        self, mock_collector: MagicMock, sample_finding: Finding
    ):
        """Test that _apply_fix calls PATCH with correct payload."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"taskUid": 456}
        mock_response.raise_for_status = MagicMock()
        mock_collector._client.patch = AsyncMock(return_value=mock_response)

        runner = FixBenchmarkRunner(mock_collector)

        await runner._apply_fix("test-index", sample_finding.fix.payload)

        mock_collector._client.patch.assert_called_once_with(
            "/indexes/test-index/settings",
            json={"searchableAttributes": ["title", "description"]},
        )

    @pytest.mark.asyncio
    async def test_apply_fix_without_client_raises(self, mock_collector: MagicMock):
        """Test _apply_fix raises when collector not connected."""
        mock_collector._client = None

        runner = FixBenchmarkRunner(mock_collector)

        with pytest.raises(RuntimeError, match="Collector not connected"):
            await runner._apply_fix("test-index", {"searchableAttributes": ["title"]})

    @pytest.mark.asyncio
    async def test_revert_settings_calls_put(self, mock_collector: MagicMock):
        """Test that _revert_settings calls PUT with original settings."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"taskUid": 789}
        mock_response.raise_for_status = MagicMock()
        mock_collector._client.put = AsyncMock(return_value=mock_response)

        runner = FixBenchmarkRunner(mock_collector)
        original_settings = {"searchableAttributes": ["*"], "filterableAttributes": []}

        await runner._revert_settings("test-index", original_settings)

        mock_collector._client.put.assert_called_once_with(
            "/indexes/test-index/settings",
            json=original_settings,
        )

    @pytest.mark.asyncio
    async def test_revert_settings_without_client_raises(
        self, mock_collector: MagicMock
    ):
        """Test _revert_settings raises when collector not connected."""
        mock_collector._client = None

        runner = FixBenchmarkRunner(mock_collector)

        with pytest.raises(RuntimeError, match="Collector not connected"):
            await runner._revert_settings("test-index", {})

    @pytest.mark.asyncio
    async def test_benchmark_calculates_improvement(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        sample_finding: Finding,
    ):
        """Test that improvement percentage is calculated correctly."""
        # First call returns slower results (before), second call returns faster (after)
        call_count = 0

        async def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate improvement: before=20ms, after=10ms
            return {
                "hits": [{"id": 1}],
                "totalHits": 10,
                "processingTimeMs": 20 if call_count <= 3 else 10,
            }

        mock_collector.search = mock_search

        mock_patch_response = MagicMock()
        mock_patch_response.json.return_value = {"taskUid": 123}
        mock_patch_response.raise_for_status = MagicMock()
        mock_collector._client.patch = AsyncMock(return_value=mock_patch_response)

        mock_put_response = MagicMock()
        mock_put_response.json.return_value = {"taskUid": 124}
        mock_put_response.raise_for_status = MagicMock()
        mock_collector._client.put = AsyncMock(return_value=mock_put_response)

        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"isIndexing": False}
        mock_get_response.raise_for_status = MagicMock()
        mock_collector._client.get = AsyncMock(return_value=mock_get_response)

        runner = FixBenchmarkRunner(mock_collector, seed=42)

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=sample_finding,
            apply=True,
        )

        # Both before and after benchmarks should have been run
        assert result.before_benchmark is not None
        assert result.after_benchmark is not None
        # improvement_percent should be set (exact value depends on latency measurements)
        assert result.improvement_percent is not None

    @pytest.mark.asyncio
    async def test_indexing_timeout_still_reverts(
        self,
        mock_collector: MagicMock,
        sample_index: IndexData,
        sample_finding: Finding,
    ):
        """Test that settings are reverted even if indexing times out."""
        mock_patch_response = MagicMock()
        mock_patch_response.json.return_value = {"taskUid": 123}
        mock_patch_response.raise_for_status = MagicMock()
        mock_collector._client.patch = AsyncMock(return_value=mock_patch_response)

        mock_put_response = MagicMock()
        mock_put_response.json.return_value = {"taskUid": 124}
        mock_put_response.raise_for_status = MagicMock()
        mock_collector._client.put = AsyncMock(return_value=mock_put_response)

        # Make indexing always return True (indexing)
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"isIndexing": True}
        mock_get_response.raise_for_status = MagicMock()
        mock_collector._client.get = AsyncMock(return_value=mock_get_response)

        runner = FixBenchmarkRunner(mock_collector, seed=42)
        # Set very short timeout for testing
        runner.MAX_INDEXING_WAIT = 0.01
        runner.INDEXING_POLL_INTERVAL = 0.001

        result = await runner.benchmark_fix(
            index=sample_index,
            finding=sample_finding,
            apply=True,
            revert_after=True,
        )

        assert result.applied is True
        assert result.reverted is True
        assert "still indexing" in result.error
        # PUT should have been called to revert
        mock_collector._client.put.assert_called_once()
