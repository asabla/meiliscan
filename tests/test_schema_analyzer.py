"""Tests for the Schema Analyzer."""

import pytest

from meilisearch_analyzer.analyzers.schema_analyzer import SchemaAnalyzer
from meilisearch_analyzer.models.finding import FindingCategory, FindingSeverity
from meilisearch_analyzer.models.index import IndexData, IndexSettings, IndexStats, PaginationSettings


class TestSchemaAnalyzer:
    """Tests for SchemaAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> SchemaAnalyzer:
        """Create a schema analyzer instance."""
        return SchemaAnalyzer()

    @pytest.fixture
    def basic_index(self) -> IndexData:
        """Create a basic index for testing."""
        return IndexData(
            uid="test_index",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=1000,
                fieldDistribution={
                    "id": 1000,
                    "title": 1000,
                    "description": 900,
                    "price": 1000,
                    "category": 800,
                },
            ),
        )

    def test_analyzer_name(self, analyzer):
        """Test analyzer name property."""
        assert analyzer.name == "schema"

    def test_wildcard_searchable_attributes(self, analyzer, basic_index):
        """Test detection of wildcard searchable attributes (S001)."""
        findings = analyzer.analyze(basic_index)
        
        s001_findings = [f for f in findings if f.id == "MEILI-S001"]
        assert len(s001_findings) == 1
        
        finding = s001_findings[0]
        assert finding.severity == FindingSeverity.CRITICAL
        assert finding.category == FindingCategory.SCHEMA
        assert finding.current_value == ["*"]
        assert finding.index_uid == "test_index"

    def test_no_wildcard_searchable_attributes(self, analyzer):
        """Test no S001 finding when searchable attributes are explicit."""
        index = IndexData(
            uid="test",
            settings=IndexSettings(
                searchableAttributes=["title", "description"],
            ),
            stats=IndexStats(
                numberOfDocuments=100,
                fieldDistribution={"id": 100, "title": 100, "description": 100},
            ),
        )
        
        findings = analyzer.analyze(index)
        s001_findings = [f for f in findings if f.id == "MEILI-S001"]
        assert len(s001_findings) == 0

    def test_id_fields_in_searchable_attributes(self, analyzer):
        """Test detection of ID fields in searchable attributes (S002)."""
        index = IndexData(
            uid="test",
            settings=IndexSettings(
                searchableAttributes=["id", "title", "user_id", "description"],
            ),
            stats=IndexStats(
                numberOfDocuments=100,
                fieldDistribution={"id": 100, "title": 100, "user_id": 100, "description": 100},
            ),
        )
        
        findings = analyzer.analyze(index)
        s002_findings = [f for f in findings if f.id == "MEILI-S002"]
        assert len(s002_findings) == 1
        assert s002_findings[0].severity == FindingSeverity.WARNING

    def test_empty_filterable_attributes(self, analyzer, basic_index):
        """Test detection of empty filterable attributes (S004)."""
        findings = analyzer.analyze(basic_index)
        
        s004_findings = [f for f in findings if f.id == "MEILI-S004"]
        assert len(s004_findings) == 1
        assert s004_findings[0].severity == FindingSeverity.INFO

    def test_no_stop_words(self, analyzer, basic_index):
        """Test detection of missing stop words (S006)."""
        findings = analyzer.analyze(basic_index)
        
        s006_findings = [f for f in findings if f.id == "MEILI-S006"]
        assert len(s006_findings) == 1
        assert s006_findings[0].severity == FindingSeverity.SUGGESTION

    def test_default_ranking_rules(self, analyzer, basic_index):
        """Test detection of default ranking rules (S007)."""
        findings = analyzer.analyze(basic_index)
        
        s007_findings = [f for f in findings if f.id == "MEILI-S007"]
        assert len(s007_findings) == 1
        assert s007_findings[0].severity == FindingSeverity.INFO

    def test_no_distinct_attribute(self, analyzer):
        """Test detection of missing distinct attribute (S008)."""
        # S008 only triggers when document count > 1000
        index = IndexData(
            uid="test",
            settings=IndexSettings(searchableAttributes=["title"]),  # Avoid S001
            stats=IndexStats(
                numberOfDocuments=2000,
                fieldDistribution={"id": 2000, "title": 2000},
            ),
        )
        
        findings = analyzer.analyze(index)
        s008_findings = [f for f in findings if f.id == "MEILI-S008"]
        assert len(s008_findings) == 1
        assert s008_findings[0].severity == FindingSeverity.SUGGESTION

    def test_low_pagination_limit(self, analyzer):
        """Test detection of low pagination limit (S009)."""
        index = IndexData(
            uid="test",
            settings=IndexSettings(
                searchableAttributes=["title"],  # Avoid S001
                pagination=PaginationSettings(maxTotalHits=50),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )
        
        findings = analyzer.analyze(index)
        s009_findings = [f for f in findings if f.id == "MEILI-S009"]
        assert len(s009_findings) == 1
        assert s009_findings[0].severity == FindingSeverity.WARNING
        assert s009_findings[0].current_value == 50

    def test_high_pagination_limit(self, analyzer):
        """Test detection of high pagination limit (S010)."""
        index = IndexData(
            uid="test",
            settings=IndexSettings(
                searchableAttributes=["title"],  # Avoid S001
                pagination=PaginationSettings(maxTotalHits=50000),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )
        
        findings = analyzer.analyze(index)
        s010_findings = [f for f in findings if f.id == "MEILI-S010"]
        assert len(s010_findings) == 1
        assert s010_findings[0].severity == FindingSeverity.SUGGESTION

    def test_well_configured_index(self, analyzer):
        """Test that well-configured index has fewer findings."""
        index = IndexData(
            uid="well_configured",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "description", "content"],
                filterableAttributes=["category", "price", "status"],
                sortableAttributes=["price", "created_at"],
                stopWords=["the", "a", "an", "is", "are"],
                distinctAttribute="id",
                rankingRules=["words", "typo", "proximity", "attribute", "sort:price:desc", "exactness"],
            ),
            stats=IndexStats(
                numberOfDocuments=5000,
                fieldDistribution={
                    "id": 5000,
                    "title": 5000,
                    "description": 4500,
                    "content": 5000,
                    "category": 5000,
                    "price": 5000,
                    "status": 5000,
                    "created_at": 5000,
                },
            ),
        )
        
        findings = analyzer.analyze(index)
        
        # Should not have S001 (wildcard), S004 (empty filterable), S006 (stop words), S008 (distinct)
        finding_ids = {f.id for f in findings}
        assert "MEILI-S001" not in finding_ids
        assert "MEILI-S004" not in finding_ids
        assert "MEILI-S006" not in finding_ids
        assert "MEILI-S008" not in finding_ids

    def test_finding_has_fix(self, analyzer, basic_index):
        """Test that critical findings have fix suggestions."""
        findings = analyzer.analyze(basic_index)
        
        s001 = next((f for f in findings if f.id == "MEILI-S001"), None)
        assert s001 is not None
        assert s001.fix is not None
        assert s001.fix.type == "settings_update"
        assert s001.fix.endpoint.startswith("PATCH")

    def test_is_id_field_detection(self, analyzer):
        """Test ID field detection patterns."""
        assert analyzer._is_id_field("id") is True
        assert analyzer._is_id_field("_id") is True
        assert analyzer._is_id_field("user_id") is True
        assert analyzer._is_id_field("userId") is True
        assert analyzer._is_id_field("UUID") is True
        assert analyzer._is_id_field("guid") is True
        assert analyzer._is_id_field("title") is False
        assert analyzer._is_id_field("description") is False

    def test_numeric_field_detection(self, analyzer):
        """Test numeric field detection."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"price": 10.99, "quantity": 5},
                {"price": 20.50, "quantity": 10},
            ],
        )
        
        assert analyzer._is_likely_numeric_only("price", index) is True
        assert analyzer._is_likely_numeric_only("quantity", index) is True
        
        # Test pattern-based detection
        empty_index = IndexData(uid="test")
        assert analyzer._is_likely_numeric_only("price", empty_index) is True
        assert analyzer._is_likely_numeric_only("amount", empty_index) is True
        assert analyzer._is_likely_numeric_only("title", empty_index) is False
