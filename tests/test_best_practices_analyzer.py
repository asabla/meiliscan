"""Tests for BestPracticesAnalyzer."""

import pytest

from meilisearch_analyzer.analyzers.best_practices import (
    BestPracticesAnalyzer,
    CURRENT_STABLE_VERSION,
)
from meilisearch_analyzer.models.finding import FindingCategory, FindingSeverity
from meilisearch_analyzer.models.index import IndexData, IndexSettings, IndexStats


@pytest.fixture
def analyzer():
    """Create a BestPracticesAnalyzer instance."""
    return BestPracticesAnalyzer()


@pytest.fixture
def basic_index():
    """Create a basic index for testing."""
    return IndexData(
        uid="test_index",
        primaryKey="id",
        settings=IndexSettings(
            searchableAttributes=["title", "description"],
            filterableAttributes=["category", "status"],
        ),
        stats=IndexStats(
            numberOfDocuments=1000,
            fieldDistribution={"id": 1000, "title": 1000, "description": 1000},
        ),
    )


class TestBestPracticesAnalyzer:
    """Tests for BestPracticesAnalyzer."""

    def test_analyzer_name(self, analyzer):
        """Test analyzer name property."""
        assert analyzer.name == "best_practices"

    # B002: Duplicate searchable/filterable attributes tests

    def test_duplicate_searchable_filterable_b002(self, analyzer):
        """Test detection of fields in both searchable and filterable (B002)."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "description", "category"],
                filterableAttributes=["category", "brand", "price"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        b002_findings = [f for f in findings if f.id == "MEILI-B002"]

        assert len(b002_findings) == 1
        assert b002_findings[0].severity == FindingSeverity.SUGGESTION
        assert b002_findings[0].category == FindingCategory.BEST_PRACTICES
        assert "category" in str(b002_findings[0].current_value)

    def test_no_duplicate_searchable_filterable(self, analyzer):
        """Test no finding when searchable and filterable are distinct."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "description"],
                filterableAttributes=["category", "brand", "price"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        b002_findings = [f for f in findings if f.id == "MEILI-B002"]

        assert len(b002_findings) == 0

    def test_skip_duplicate_check_with_wildcard(self, analyzer):
        """Test that B002 is skipped when searchable is wildcard."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["*"],
                filterableAttributes=["category"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        b002_findings = [f for f in findings if f.id == "MEILI-B002"]

        # Should be skipped since S001 covers wildcard
        assert len(b002_findings) == 0

    def test_multiple_duplicate_fields(self, analyzer):
        """Test detection of multiple duplicate fields."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "description", "category", "tags"],
                filterableAttributes=["category", "tags", "price"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        b002_findings = [f for f in findings if f.id == "MEILI-B002"]

        assert len(b002_findings) == 1
        duplicates = b002_findings[0].current_value["duplicates"]
        assert "category" in duplicates
        assert "tags" in duplicates

    # B001: Settings after documents tests

    def test_settings_after_documents_b001(self, analyzer):
        """Test detection of settings updated after documents added (B001)."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(numberOfDocuments=1000),
        )

        tasks = [
            {
                "uid": 1,
                "indexUid": "products",
                "type": "documentAdditionOrUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T10:00:00Z",
            },
            {
                "uid": 2,
                "indexUid": "products",
                "type": "settingsUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T11:00:00Z",
                "details": {"searchableAttributes": ["title"]},
            },
        ]

        findings = analyzer.analyze_global([index], {}, tasks, None)
        b001_findings = [f for f in findings if f.id == "MEILI-B001"]

        assert len(b001_findings) == 1
        assert b001_findings[0].severity == FindingSeverity.WARNING
        assert b001_findings[0].category == FindingCategory.BEST_PRACTICES
        assert b001_findings[0].index_uid == "products"

    def test_no_settings_after_documents(self, analyzer):
        """Test no finding when settings are configured before documents."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(numberOfDocuments=1000),
        )

        tasks = [
            {
                "uid": 1,
                "indexUid": "products",
                "type": "settingsUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T09:00:00Z",
            },
            {
                "uid": 2,
                "indexUid": "products",
                "type": "documentAdditionOrUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T10:00:00Z",
            },
        ]

        findings = analyzer.analyze_global([index], {}, tasks, None)
        b001_findings = [f for f in findings if f.id == "MEILI-B001"]

        assert len(b001_findings) == 0

    def test_no_tasks_no_b001_finding(self, analyzer):
        """Test no B001 finding when no tasks are available."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(numberOfDocuments=1000),
        )

        findings = analyzer.analyze_global([index], {}, None, None)
        b001_findings = [f for f in findings if f.id == "MEILI-B001"]

        assert len(b001_findings) == 0

    def test_multiple_settings_updates_after_documents(self, analyzer):
        """Test counting multiple settings updates after documents."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(numberOfDocuments=1000),
        )

        tasks = [
            {
                "uid": 1,
                "indexUid": "products",
                "type": "documentAdditionOrUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T10:00:00Z",
            },
            {
                "uid": 2,
                "indexUid": "products",
                "type": "settingsUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T11:00:00Z",
                "details": {"searchableAttributes": ["title"]},
            },
            {
                "uid": 3,
                "indexUid": "products",
                "type": "settingsUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T12:00:00Z",
                "details": {"filterableAttributes": ["category"]},
            },
        ]

        findings = analyzer.analyze_global([index], {}, tasks, None)
        b001_findings = [f for f in findings if f.id == "MEILI-B001"]

        assert len(b001_findings) == 1
        assert b001_findings[0].current_value["settings_updates_after_docs"] == 2

    # B003: Missing embedders tests

    def test_missing_embedders_b003(self, analyzer):
        """Test detection of text-heavy indexes without embedders (B003)."""
        index = IndexData(
            uid="articles",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=500,
                fieldDistribution={
                    "id": 500,
                    "title": 500,
                    "content": 500,
                    "body": 500,
                },
            ),
        )

        findings = analyzer.analyze_global([index], {}, None, None)
        b003_findings = [f for f in findings if f.id == "MEILI-B003"]

        assert len(b003_findings) == 1
        assert b003_findings[0].severity == FindingSeverity.INFO
        assert "articles" in str(b003_findings[0].current_value)

    def test_no_embedders_finding_for_small_index(self, analyzer):
        """Test no B003 finding for small indexes."""
        index = IndexData(
            uid="articles",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=50,  # Below threshold
                fieldDistribution={"id": 50, "content": 50},
            ),
        )

        findings = analyzer.analyze_global([index], {}, None, None)
        b003_findings = [f for f in findings if f.id == "MEILI-B003"]

        assert len(b003_findings) == 0

    def test_no_embedders_finding_without_text_fields(self, analyzer):
        """Test no B003 finding for indexes without text-heavy fields."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=1000,
                fieldDistribution={
                    "id": 1000,
                    "name": 1000,
                    "price": 1000,
                    "category": 1000,
                },
            ),
        )

        findings = analyzer.analyze_global([index], {}, None, None)
        b003_findings = [f for f in findings if f.id == "MEILI-B003"]

        assert len(b003_findings) == 0

    # B004: Old version tests

    def test_old_version_major_b004(self, analyzer):
        """Test detection of outdated major version (B004)."""
        findings = analyzer.analyze_global([], {}, None, "0.30.0")
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        assert len(b004_findings) == 1
        assert b004_findings[0].severity == FindingSeverity.WARNING
        assert "0.30.0" in b004_findings[0].description

    def test_old_version_minor_b004(self, analyzer):
        """Test detection of outdated minor version (B004)."""
        # Current is 1.12.0, test with 1.10.0
        findings = analyzer.analyze_global([], {}, None, "1.10.0")
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        assert len(b004_findings) == 1
        assert b004_findings[0].severity == FindingSeverity.SUGGESTION

    def test_current_version_no_finding(self, analyzer):
        """Test no finding when running current version."""
        findings = analyzer.analyze_global([], {}, None, CURRENT_STABLE_VERSION)
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        assert len(b004_findings) == 0

    def test_version_with_v_prefix(self, analyzer):
        """Test version parsing with 'v' prefix."""
        findings = analyzer.analyze_global([], {}, None, "v0.30.0")
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        assert len(b004_findings) == 1

    def test_no_version_no_finding(self, analyzer):
        """Test no finding when version is not available."""
        findings = analyzer.analyze_global([], {}, None, None)
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        assert len(b004_findings) == 0

    def test_invalid_version_no_finding(self, analyzer):
        """Test no finding when version string is invalid."""
        findings = analyzer.analyze_global([], {}, None, "invalid-version")
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        # Should not crash, just skip the check
        assert len(b004_findings) == 0

    # Combined tests

    def test_multiple_global_findings(self, analyzer):
        """Test generating multiple global findings."""
        index = IndexData(
            uid="articles",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=500,
                fieldDistribution={"id": 500, "content": 500},
            ),
        )

        tasks = [
            {
                "uid": 1,
                "indexUid": "articles",
                "type": "documentAdditionOrUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T10:00:00Z",
            },
            {
                "uid": 2,
                "indexUid": "articles",
                "type": "settingsUpdate",
                "status": "succeeded",
                "enqueuedAt": "2024-01-01T11:00:00Z",
            },
        ]

        findings = analyzer.analyze_global([index], {}, tasks, "0.30.0")

        # Should have B001, B003, and B004
        finding_ids = {f.id for f in findings}
        assert "MEILI-B001" in finding_ids
        assert "MEILI-B003" in finding_ids
        assert "MEILI-B004" in finding_ids

    def test_per_index_and_global_findings(self, analyzer):
        """Test that per-index analysis works alongside global analysis."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "category"],
                filterableAttributes=["category", "price"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        # Per-index findings
        per_index_findings = analyzer.analyze(index)
        b002_findings = [f for f in per_index_findings if f.id == "MEILI-B002"]
        assert len(b002_findings) == 1

        # Global findings
        global_findings = analyzer.analyze_global([index], {}, None, "0.30.0")
        b004_findings = [f for f in global_findings if f.id == "MEILI-B004"]
        assert len(b004_findings) == 1

    def test_finding_references(self, analyzer):
        """Test that findings include reference URLs."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "category"],
                filterableAttributes=["category"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        b002_findings = [f for f in findings if f.id == "MEILI-B002"]

        assert len(b002_findings) == 1
        assert len(b002_findings[0].references) > 0
        assert any("meilisearch.com" in ref for ref in b002_findings[0].references)

    def test_b004_includes_update_reference(self, analyzer):
        """Test that B004 includes update documentation reference."""
        findings = analyzer.analyze_global([], {}, None, "0.30.0")
        b004_findings = [f for f in findings if f.id == "MEILI-B004"]

        assert len(b004_findings) == 1
        assert any("updating" in ref.lower() or "releases" in ref.lower() 
                   for ref in b004_findings[0].references)
