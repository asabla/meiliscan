"""Tests for SearchProbeAnalyzer."""

import pytest

from meiliscan.analyzers.search_probe_analyzer import ProbeResult, SearchProbeAnalyzer
from meiliscan.models.finding import FindingCategory, FindingSeverity
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


@pytest.fixture
def analyzer():
    """Create a SearchProbeAnalyzer instance."""
    return SearchProbeAnalyzer()


@pytest.fixture
def basic_index():
    """Create a basic index for testing."""
    return IndexData(
        uid="products",
        primaryKey="id",
        settings=IndexSettings(
            searchableAttributes=["title", "description"],
            filterableAttributes=["category", "brand"],
            sortableAttributes=["price", "created_at"],
        ),
        stats=IndexStats(
            numberOfDocuments=1000,
            fieldDistribution={"id": 1000, "title": 1000, "price": 1000},
        ),
        sample_documents=[
            {
                "id": "1",
                "title": "Product 1",
                "category": "electronics",
                "price": 99.99,
            },
            {"id": "2", "title": "Product 2", "category": "books", "price": 19.99},
        ],
    )


class TestSearchProbeAnalyzer:
    """Tests for SearchProbeAnalyzer."""

    def test_analyzer_name(self, analyzer):
        """Test analyzer name property."""
        assert analyzer.name == "search_probe"

    # Q001: Sort probe failure tests

    @pytest.mark.asyncio
    async def test_sort_probe_failure_q001(self, analyzer, basic_index):
        """Test detection of sort probe failure (Q001)."""

        async def mock_search(index_uid, query, filter, sort):
            if sort:
                raise Exception("Invalid sort attribute: price")
            return {"hits": []}

        findings, results = await analyzer.analyze([basic_index], mock_search)
        q001_findings = [f for f in findings if f.id == "MEILI-Q001"]

        assert len(q001_findings) >= 1
        assert q001_findings[0].severity == FindingSeverity.WARNING
        assert q001_findings[0].category == FindingCategory.SEARCH_PROBE
        assert "sort" in q001_findings[0].title.lower()

    @pytest.mark.asyncio
    async def test_sort_probe_success_no_q001(self, analyzer, basic_index):
        """Test no Q001 when sort probe succeeds."""

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": []}

        findings, results = await analyzer.analyze([basic_index], mock_search)
        q001_findings = [f for f in findings if f.id == "MEILI-Q001"]

        assert len(q001_findings) == 0

    # Q002: Filter probe failure tests

    @pytest.mark.asyncio
    async def test_filter_probe_failure_q002(self, analyzer):
        """Test detection of filter probe failure (Q002)."""
        # Use an index with only filterable attrs (no sortable) to ensure
        # filter probes run within MAX_PROBES_PER_INDEX limit
        filter_only_index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                filterableAttributes=["category", "brand"],
                sortableAttributes=[],  # No sortable attrs
            ),
            stats=IndexStats(numberOfDocuments=1000),
            sample_documents=[
                {"id": "1", "category": "electronics", "brand": "acme"},
            ],
        )

        async def mock_search(index_uid, query, filter, sort):
            if filter:
                raise Exception("Invalid filter syntax")
            return {"hits": []}

        findings, results = await analyzer.analyze([filter_only_index], mock_search)
        q002_findings = [f for f in findings if f.id == "MEILI-Q002"]

        assert len(q002_findings) >= 1
        assert q002_findings[0].severity == FindingSeverity.WARNING
        assert "filter" in q002_findings[0].title.lower()

    @pytest.mark.asyncio
    async def test_filter_probe_success_no_q002(self, analyzer):
        """Test no Q002 when filter probe succeeds."""
        # Use an index with only filterable attrs to ensure filter probes run
        filter_only_index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                filterableAttributes=["category"],
                sortableAttributes=[],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[{"id": "1", "category": "books"}],
        )

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": []}

        findings, results = await analyzer.analyze([filter_only_index], mock_search)
        q002_findings = [f for f in findings if f.id == "MEILI-Q002"]

        assert len(q002_findings) == 0

    # Q003: Large response payload tests

    @pytest.mark.asyncio
    async def test_large_response_q003(self, analyzer, basic_index):
        """Test detection of large response payload (Q003)."""

        async def mock_search(index_uid, query, filter, sort):
            # Return a large payload (> 100KB)
            large_data = {"content": "x" * 150000}
            return {"hits": [large_data]}

        findings, results = await analyzer.analyze([basic_index], mock_search)
        q003_findings = [f for f in findings if f.id == "MEILI-Q003"]

        assert len(q003_findings) == 1
        assert q003_findings[0].severity == FindingSeverity.INFO
        assert "large" in q003_findings[0].title.lower()

    @pytest.mark.asyncio
    async def test_normal_response_no_q003(self, analyzer, basic_index):
        """Test no Q003 when response is normal sized."""

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": [{"id": "1", "title": "Test"}]}

        findings, results = await analyzer.analyze([basic_index], mock_search)
        q003_findings = [f for f in findings if f.id == "MEILI-Q003"]

        assert len(q003_findings) == 0

    # Probe result tests

    @pytest.mark.asyncio
    async def test_returns_probe_results(self, analyzer, basic_index):
        """Test that analyze returns probe results."""

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": []}

        findings, results = await analyzer.analyze([basic_index], mock_search)

        assert len(results) > 0
        assert all(isinstance(r, ProbeResult) for r in results)

    @pytest.mark.asyncio
    async def test_probe_result_contains_index_uid(self, analyzer, basic_index):
        """Test that probe results contain index UID."""

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": []}

        findings, results = await analyzer.analyze([basic_index], mock_search)

        assert all(r.index_uid == "products" for r in results)

    @pytest.mark.asyncio
    async def test_max_probes_per_index(self, analyzer):
        """Test that probes are limited per index."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                sortableAttributes=["a", "b", "c", "d", "e"],
                filterableAttributes=["x", "y", "z"],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[{"id": "1", "x": "val", "y": "val", "z": "val"}],
        )

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": []}

        findings, results = await analyzer.analyze([index], mock_search)

        # Should be limited to MAX_PROBES_PER_INDEX (3)
        assert len(results) <= analyzer.MAX_PROBES_PER_INDEX

    @pytest.mark.asyncio
    async def test_no_probes_without_sortable_or_filterable(self, analyzer):
        """Test behavior with no sortable or filterable attributes."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                sortableAttributes=[],
                filterableAttributes=[],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        async def mock_search(index_uid, query, filter, sort):
            return {"hits": []}

        findings, results = await analyzer.analyze([index], mock_search)

        # Should only have basic search probe
        assert len(results) == 1
        assert results[0].probe_type == "basic"


class TestProbeResult:
    """Tests for ProbeResult dataclass."""

    def test_probe_result_creation(self):
        """Test creating a ProbeResult."""
        result = ProbeResult(
            index_uid="test",
            probe_type="sort",
            success=True,
            field="price",
        )

        assert result.index_uid == "test"
        assert result.probe_type == "sort"
        assert result.success is True
        assert result.field == "price"

    def test_probe_result_with_error(self):
        """Test ProbeResult with error message."""
        result = ProbeResult(
            index_uid="test",
            probe_type="filter",
            success=False,
            field="category",
            error_message="Invalid filter",
        )

        assert result.success is False
        assert result.error_message == "Invalid filter"

    def test_probe_result_with_response_data(self):
        """Test ProbeResult with response metrics."""
        result = ProbeResult(
            index_uid="test",
            probe_type="basic",
            success=True,
            response_size_bytes=50000,
            hit_count=20,
        )

        assert result.response_size_bytes == 50000
        assert result.hit_count == 20


class TestFindFilterValue:
    """Tests for _find_filter_value helper."""

    def test_find_simple_value(self, analyzer):
        """Test finding a simple filter value."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(),
            sample_documents=[
                {"id": "1", "category": "electronics"},
            ],
        )

        value = analyzer._find_filter_value(index, "category")
        assert value == "electronics"

    def test_find_value_skips_none(self, analyzer):
        """Test that None values are skipped."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(),
            sample_documents=[
                {"id": "1", "category": None},
                {"id": "2", "category": "books"},
            ],
        )

        value = analyzer._find_filter_value(index, "category")
        assert value == "books"

    def test_find_value_skips_complex_types(self, analyzer):
        """Test that complex types (list, dict) are skipped."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(),
            sample_documents=[
                {"id": "1", "tags": ["a", "b"]},  # list - skip
                {"id": "2", "meta": {"key": "val"}},  # dict - skip
                {"id": "3", "tags": "simple"},
            ],
        )

        value = analyzer._find_filter_value(index, "tags")
        assert value == "simple"

    def test_find_value_missing_field(self, analyzer):
        """Test returns None for missing field."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(),
            sample_documents=[
                {"id": "1", "title": "Test"},
            ],
        )

        value = analyzer._find_filter_value(index, "nonexistent")
        assert value is None


class TestGetNestedValue:
    """Tests for _get_nested_value helper."""

    def test_simple_field(self, analyzer):
        """Test getting simple field value."""
        doc = {"name": "John"}
        assert analyzer._get_nested_value(doc, "name") == "John"

    def test_nested_field(self, analyzer):
        """Test getting nested field value."""
        doc = {"user": {"name": "John"}}
        assert analyzer._get_nested_value(doc, "user.name") == "John"

    def test_deeply_nested_field(self, analyzer):
        """Test getting deeply nested field value."""
        doc = {"a": {"b": {"c": "value"}}}
        assert analyzer._get_nested_value(doc, "a.b.c") == "value"

    def test_missing_nested_field(self, analyzer):
        """Test returns None for missing nested field."""
        doc = {"user": {"name": "John"}}
        assert analyzer._get_nested_value(doc, "user.email") is None

    def test_missing_intermediate_field(self, analyzer):
        """Test returns None for missing intermediate field."""
        doc = {"user": {"name": "John"}}
        assert analyzer._get_nested_value(doc, "profile.name") is None
