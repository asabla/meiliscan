"""Tests for Index models."""

from datetime import datetime


from meiliscan.models.index import (
    IndexData,
    IndexSettings,
    IndexStats,
    TypoToleranceSettings,
)


class TestTypoToleranceSettings:
    """Tests for TypoToleranceSettings."""

    def test_default_values(self):
        """Test default typo tolerance settings."""
        settings = TypoToleranceSettings()
        assert settings.enabled is True
        assert settings.min_word_size_for_typos == {"oneTypo": 5, "twoTypos": 9}
        assert settings.disable_on_words == []
        assert settings.disable_on_attributes == []

    def test_custom_values(self):
        """Test custom typo tolerance settings."""
        settings = TypoToleranceSettings(
            enabled=False,
            disableOnWords=["test"],
        )
        assert settings.enabled is False
        assert settings.disable_on_words == ["test"]


class TestIndexSettings:
    """Tests for IndexSettings."""

    def test_default_settings(self):
        """Test default index settings."""
        settings = IndexSettings()
        assert settings.displayed_attributes == ["*"]
        assert settings.searchable_attributes == ["*"]
        assert settings.filterable_attributes == []
        assert settings.sortable_attributes == []
        assert settings.ranking_rules == [
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness",
        ]
        assert settings.stop_words == []
        assert settings.synonyms == {}
        assert settings.distinct_attribute is None

    def test_custom_settings(self):
        """Test custom index settings."""
        settings = IndexSettings(
            searchableAttributes=["title", "content"],
            filterableAttributes=["category"],
        )
        assert settings.searchable_attributes == ["title", "content"]
        assert settings.filterable_attributes == ["category"]

    def test_settings_from_api_response(self):
        """Test creating settings from API response format."""
        api_response = {
            "displayedAttributes": ["*"],
            "searchableAttributes": ["title", "body"],
            "filterableAttributes": ["category", "price"],
            "sortableAttributes": ["price"],
            "rankingRules": ["words", "typo"],
            "stopWords": ["the", "a"],
            "synonyms": {"car": ["vehicle"]},
            "distinctAttribute": "id",
            "typoTolerance": {
                "enabled": True,
                "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8},
            },
            "faceting": {"maxValuesPerFacet": 200},
            "pagination": {"maxTotalHits": 5000},
            "proximityPrecision": "byAttribute",
        }

        settings = IndexSettings(**api_response)
        assert settings.searchable_attributes == ["title", "body"]
        assert settings.filterable_attributes == ["category", "price"]
        assert settings.stop_words == ["the", "a"]
        assert settings.pagination.max_total_hits == 5000


class TestIndexStats:
    """Tests for IndexStats."""

    def test_default_stats(self):
        """Test default stats."""
        stats = IndexStats()
        assert stats.number_of_documents == 0
        assert stats.is_indexing is False
        assert stats.field_distribution == {}

    def test_stats_from_api_response(self):
        """Test creating stats from API response."""
        api_response = {
            "numberOfDocuments": 1000,
            "isIndexing": False,
            "fieldDistribution": {
                "id": 1000,
                "title": 1000,
                "description": 980,
            },
        }

        stats = IndexStats(**api_response)
        assert stats.number_of_documents == 1000
        assert stats.is_indexing is False
        assert stats.field_distribution["id"] == 1000
        assert stats.field_distribution["description"] == 980


class TestIndexData:
    """Tests for IndexData."""

    def test_index_creation(self):
        """Test creating index data."""
        index = IndexData(
            uid="products",
            primaryKey="id",
        )
        assert index.uid == "products"
        assert index.primary_key == "id"

    def test_index_with_full_data(self):
        """Test index with settings and stats."""
        settings = IndexSettings(
            searchableAttributes=["title"],
            filterableAttributes=["category"],
        )
        stats = IndexStats(
            numberOfDocuments=500,
            fieldDistribution={"id": 500, "title": 500, "category": 450},
        )

        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=settings,
            stats=stats,
        )

        assert index.document_count == 500
        assert index.field_count == 3

    def test_index_from_api_response(self):
        """Test creating index from API-style response."""
        index = IndexData(
            uid="movies",
            primaryKey="id",
            createdAt=datetime(2024, 1, 1, 0, 0, 0),
            updatedAt=datetime(2024, 1, 2, 0, 0, 0),
        )
        assert index.uid == "movies"
        assert index.primary_key == "id"
        assert index.created_at is not None

    def test_document_count_property(self):
        """Test document_count property."""
        index = IndexData(
            uid="test",
            stats=IndexStats(numberOfDocuments=100),
        )
        assert index.document_count == 100

    def test_field_count_property(self):
        """Test field_count property."""
        index = IndexData(
            uid="test",
            stats=IndexStats(fieldDistribution={"a": 10, "b": 10, "c": 10}),
        )
        assert index.field_count == 3

    def test_sample_documents(self):
        """Test sample documents storage."""
        docs = [
            {"id": 1, "title": "Test 1"},
            {"id": 2, "title": "Test 2"},
        ]
        index = IndexData(uid="test", sample_documents=docs)
        assert len(index.sample_documents) == 2
        assert index.sample_documents[0]["title"] == "Test 1"
