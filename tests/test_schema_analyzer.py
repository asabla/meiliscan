"""Tests for the Schema Analyzer."""

import pytest

from meiliscan.analyzers.schema_analyzer import SchemaAnalyzer
from meiliscan.models.finding import FindingCategory, FindingSeverity
from meiliscan.models.index import (
    IndexData,
    IndexSettings,
    IndexStats,
    PaginationSettings,
)


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
                fieldDistribution={
                    "id": 100,
                    "title": 100,
                    "user_id": 100,
                    "description": 100,
                },
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
                rankingRules=[
                    "words",
                    "typo",
                    "proximity",
                    "attribute",
                    "sort:price:desc",
                    "exactness",
                ],
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

    # S011: Primary key tests

    def test_no_primary_key_s011(self, analyzer):
        """Test detection of missing primary key (S011)."""
        index = IndexData(
            uid="test",
            primaryKey=None,
            settings=IndexSettings(searchableAttributes=["title"]),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s011_findings = [f for f in findings if f.id == "MEILI-S011"]

        assert len(s011_findings) == 1
        assert s011_findings[0].severity == FindingSeverity.CRITICAL
        assert "primary key" in s011_findings[0].title.lower()

    def test_primary_key_missing_from_docs_s011(self, analyzer):
        """Test detection of primary key field missing from documents (S011)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(searchableAttributes=["title"]),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"title": "Product 1"},  # Missing 'id'
                {"id": "2", "title": "Product 2"},
            ],
        )

        findings = analyzer.analyze(index)
        s011_findings = [f for f in findings if f.id == "MEILI-S011"]

        assert len(s011_findings) == 1
        assert "missing" in s011_findings[0].title.lower()

    def test_primary_key_present_no_s011(self, analyzer):
        """Test no S011 when primary key is properly set."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(searchableAttributes=["title"]),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": "1", "title": "Product 1"},
                {"id": "2", "title": "Product 2"},
            ],
        )

        findings = analyzer.analyze(index)
        s011_findings = [f for f in findings if f.id == "MEILI-S011"]

        assert len(s011_findings) == 0

    # S012: Mutable primary key tests

    def test_mutable_primary_key_s012(self, analyzer):
        """Test detection of mutable primary key (S012)."""
        for mutable_key in ["title", "name", "email", "status"]:
            index = IndexData(
                uid="test",
                primaryKey=mutable_key,
                settings=IndexSettings(searchableAttributes=["description"]),
                stats=IndexStats(numberOfDocuments=100),
            )

            findings = analyzer.analyze(index)
            s012_findings = [f for f in findings if f.id == "MEILI-S012"]

            assert len(s012_findings) == 1, (
                f"Expected S012 for primary key '{mutable_key}'"
            )
            assert s012_findings[0].severity == FindingSeverity.WARNING

    def test_proper_primary_key_no_s012(self, analyzer):
        """Test no S012 when primary key is a proper identifier."""
        for proper_key in ["id", "product_id", "userId", "uuid"]:
            index = IndexData(
                uid="test",
                primaryKey=proper_key,
                settings=IndexSettings(searchableAttributes=["title"]),
                stats=IndexStats(numberOfDocuments=100),
            )

            findings = analyzer.analyze(index)
            s012_findings = [f for f in findings if f.id == "MEILI-S012"]

            assert len(s012_findings) == 0, (
                f"Unexpected S012 for primary key '{proper_key}'"
            )

    # S013: No sortable attributes tests

    def test_no_sortable_with_candidates_s013(self, analyzer):
        """Test detection of missing sortable attrs with sort candidates (S013)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                sortableAttributes=[],
            ),
            stats=IndexStats(
                numberOfDocuments=100,
                fieldDistribution={
                    "id": 100,
                    "title": 100,
                    "created_at": 100,  # Sort candidate
                    "price": 100,  # Sort candidate
                },
            ),
        )

        findings = analyzer.analyze(index)
        s013_findings = [f for f in findings if f.id == "MEILI-S013"]

        assert len(s013_findings) == 1
        assert s013_findings[0].severity == FindingSeverity.INFO
        assert "sortable" in s013_findings[0].title.lower()

    def test_no_sortable_without_candidates_no_s013(self, analyzer):
        """Test no S013 when no sort candidates exist."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                sortableAttributes=[],
            ),
            stats=IndexStats(
                numberOfDocuments=100,
                fieldDistribution={"id": 100, "title": 100, "description": 100},
            ),
        )

        findings = analyzer.analyze(index)
        s013_findings = [f for f in findings if f.id == "MEILI-S013"]

        assert len(s013_findings) == 0

    # S014: Sortable type issues tests

    def test_sortable_mixed_types_s014(self, analyzer):
        """Test detection of mixed types in sortable attributes (S014)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                sortableAttributes=["price"],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": "1", "price": 19.99},  # float
                {"id": "2", "price": "29.99"},  # string
            ],
        )

        findings = analyzer.analyze(index)
        s014_findings = [f for f in findings if f.id == "MEILI-S014"]

        assert len(s014_findings) == 1
        assert s014_findings[0].severity == FindingSeverity.WARNING
        assert "inconsistent" in s014_findings[0].title.lower()

    def test_sortable_complex_types_s014(self, analyzer):
        """Test detection of complex types in sortable attributes (S014)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                sortableAttributes=["metadata"],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": "1", "metadata": {"score": 5}},  # object
                {"id": "2", "metadata": {"score": 10}},
            ],
        )

        findings = analyzer.analyze(index)
        s014_findings = [f for f in findings if f.id == "MEILI-S014"]

        assert len(s014_findings) == 1
        assert "complex" in s014_findings[0].title.lower()

    def test_sortable_consistent_types_no_s014(self, analyzer):
        """Test no S014 when sortable attributes have consistent types."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                sortableAttributes=["price"],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": "1", "price": 19.99},
                {"id": "2", "price": 29.99},
            ],
        )

        findings = analyzer.analyze(index)
        s014_findings = [f for f in findings if f.id == "MEILI-S014"]

        assert len(s014_findings) == 0

    # S015: High-cardinality filterable tests

    def test_high_cardinality_filterable_pattern_s015(self, analyzer):
        """Test detection of high-cardinality filterable by pattern (S015)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                filterableAttributes=[
                    "user_email",
                    "session_token",
                ],  # High-cardinality patterns
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s015_findings = [f for f in findings if f.id == "MEILI-S015"]

        assert len(s015_findings) == 1
        assert s015_findings[0].severity == FindingSeverity.SUGGESTION
        assert "high-cardinality" in s015_findings[0].title.lower()

    def test_high_cardinality_filterable_sample_s015(self, analyzer):
        """Test detection of high-cardinality filterable by sample analysis (S015)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                filterableAttributes=["random_code"],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": str(i), "random_code": f"code_{i}"} for i in range(10)
            ],  # All unique values
        )

        findings = analyzer.analyze(index)
        s015_findings = [f for f in findings if f.id == "MEILI-S015"]

        assert len(s015_findings) == 1

    def test_low_cardinality_filterable_no_s015(self, analyzer):
        """Test no S015 for low-cardinality filterable attributes."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                filterableAttributes=["category", "status"],
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": "1", "category": "A", "status": "active"},
                {"id": "2", "category": "B", "status": "active"},
                {"id": "3", "category": "A", "status": "inactive"},
                {"id": "4", "category": "B", "status": "active"},
                {"id": "5", "category": "C", "status": "inactive"},
            ],
        )

        findings = analyzer.analyze(index)
        s015_findings = [f for f in findings if f.id == "MEILI-S015"]

        assert len(s015_findings) == 0

    # S016: Faceting settings tests

    def test_max_values_per_facet_low_s016(self, analyzer):
        """Test detection of maxValuesPerFacet being too low (S016)."""
        from meiliscan.models.index import FacetingSettings

        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                filterableAttributes=["category"],
                faceting=FacetingSettings(maxValuesPerFacet=10),
            ),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[
                {"id": str(i), "category": f"cat_{i}"} for i in range(10)
            ],  # 10 unique categories near limit
        )

        findings = analyzer.analyze(index)
        s016_findings = [f for f in findings if f.id == "MEILI-S016"]

        # Should trigger because 10 unique values >= 10 * 0.8
        assert len(s016_findings) == 1
        assert "too low" in s016_findings[0].title.lower()

    def test_max_values_per_facet_high_s016(self, analyzer):
        """Test detection of high maxValuesPerFacet (S016)."""
        from meiliscan.models.index import FacetingSettings

        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                filterableAttributes=["category"],
                faceting=FacetingSettings(maxValuesPerFacet=1000),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s016_findings = [f for f in findings if f.id == "MEILI-S016"]

        assert len(s016_findings) == 1
        assert "high" in s016_findings[0].title.lower()

    # S017: Synonyms tests

    def test_self_synonyms_s017(self, analyzer):
        """Test detection of self-synonyms (S017)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                synonyms={"laptop": ["laptop", "notebook"]},  # Self-synonym
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s017_findings = [f for f in findings if f.id == "MEILI-S017"]

        assert len(s017_findings) == 1
        assert "self-synonyms" in str(s017_findings[0].current_value)

    def test_empty_synonyms_s017(self, analyzer):
        """Test detection of empty synonym lists (S017)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                synonyms={"laptop": []},  # Empty list
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s017_findings = [f for f in findings if f.id == "MEILI-S017"]

        assert len(s017_findings) == 1
        assert "empty" in str(s017_findings[0].current_value)

    def test_large_synonyms_s017(self, analyzer):
        """Test detection of large synonym sets (S017)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                synonyms={
                    f"term_{i}": [f"syn_{i}"] for i in range(1100)
                },  # >1000 terms
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s017_findings = [f for f in findings if f.id == "MEILI-S017"]

        assert len(s017_findings) == 1
        assert "large" in str(s017_findings[0].current_value)

    def test_proper_synonyms_no_s017(self, analyzer):
        """Test no S017 for properly configured synonyms."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                synonyms={
                    "laptop": ["notebook", "computer"],
                    "phone": ["mobile", "cell"],
                },
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s017_findings = [f for f in findings if f.id == "MEILI-S017"]

        assert len(s017_findings) == 0

    # S018: Typo tolerance on ID fields tests

    def test_typo_tolerance_on_id_fields_s018(self, analyzer):
        """Test detection of typo tolerance on ID fields (S018)."""
        from meiliscan.models.index import TypoToleranceSettings

        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "user_id"],  # ID field in searchable
                typoTolerance=TypoToleranceSettings(
                    enabled=True,
                    disableOnAttributes=[],  # ID not protected
                ),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s018_findings = [f for f in findings if f.id == "MEILI-S018"]

        assert len(s018_findings) == 1
        assert s018_findings[0].severity == FindingSeverity.SUGGESTION

    def test_typo_tolerance_disabled_on_ids_no_s018(self, analyzer):
        """Test no S018 when ID fields are protected from typo tolerance."""
        from meiliscan.models.index import TypoToleranceSettings

        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title", "user_id"],
                typoTolerance=TypoToleranceSettings(
                    enabled=True,
                    disableOnAttributes=["user_id"],  # ID protected
                ),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s018_findings = [f for f in findings if f.id == "MEILI-S018"]

        assert len(s018_findings) == 0

    # S019: Permissive typo tolerance tests

    def test_permissive_typo_tolerance_s019(self, analyzer):
        """Test detection of very permissive typo tolerance (S019)."""
        from meiliscan.models.index import TypoToleranceSettings

        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                typoTolerance=TypoToleranceSettings(
                    enabled=True,
                    minWordSizeForTypos={"oneTypo": 2, "twoTypos": 3},  # Very low
                ),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s019_findings = [f for f in findings if f.id == "MEILI-S019"]

        assert len(s019_findings) == 1
        assert s019_findings[0].severity == FindingSeverity.INFO

    def test_normal_typo_tolerance_no_s019(self, analyzer):
        """Test no S019 for normal typo tolerance settings."""
        from meiliscan.models.index import TypoToleranceSettings

        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                typoTolerance=TypoToleranceSettings(
                    enabled=True,
                    minWordSizeForTypos={"oneTypo": 5, "twoTypos": 9},  # Default
                ),
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s019_findings = [f for f in findings if f.id == "MEILI-S019"]

        assert len(s019_findings) == 0

    # S020: Dictionary/tokenization tests

    def test_large_dictionary_s020(self, analyzer):
        """Test detection of large dictionary (S020)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                dictionary=[f"word_{i}" for i in range(600)],  # >500 entries
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s020_findings = [f for f in findings if f.id == "MEILI-S020"]

        assert len(s020_findings) == 1
        assert "dictionary" in s020_findings[0].title.lower()

    def test_suspicious_separators_s020(self, analyzer):
        """Test detection of suspicious separator tokens (S020)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                separatorTokens=["abc", "verylongseparator"],  # Alphanumeric and long
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s020_findings = [f for f in findings if f.id == "MEILI-S020"]

        assert len(s020_findings) == 1
        assert "suspicious" in str(s020_findings[0].current_value)

    def test_duplicate_dictionary_entries_s020(self, analyzer):
        """Test detection of duplicate dictionary entries (S020)."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                dictionary=["word1", "word2", "word1", "word3", "word2"],  # Duplicates
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s020_findings = [f for f in findings if f.id == "MEILI-S020"]

        assert len(s020_findings) == 1
        assert "duplicate" in str(s020_findings[0].current_value)

    def test_normal_dictionary_no_s020(self, analyzer):
        """Test no S020 for normal dictionary/tokenization settings."""
        index = IndexData(
            uid="test",
            primaryKey="id",
            settings=IndexSettings(
                searchableAttributes=["title"],
                dictionary=["C++", "C#"],
                separatorTokens=["@", "#"],
            ),
            stats=IndexStats(numberOfDocuments=100),
        )

        findings = analyzer.analyze(index)
        s020_findings = [f for f in findings if f.id == "MEILI-S020"]

        assert len(s020_findings) == 0
