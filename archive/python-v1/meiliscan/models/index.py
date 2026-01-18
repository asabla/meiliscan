"""Index data models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TypoToleranceSettings(BaseModel):
    """Typo tolerance settings."""

    enabled: bool = True
    min_word_size_for_typos: dict[str, int] = Field(
        default_factory=lambda: {"oneTypo": 5, "twoTypos": 9},
        alias="minWordSizeForTypos",
    )
    disable_on_words: list[str] = Field(default_factory=list, alias="disableOnWords")
    disable_on_attributes: list[str] = Field(
        default_factory=list, alias="disableOnAttributes"
    )

    model_config = {"populate_by_name": True}


class FacetingSettings(BaseModel):
    """Faceting settings."""

    max_values_per_facet: int = Field(default=100, alias="maxValuesPerFacet")

    model_config = {"populate_by_name": True}


class PaginationSettings(BaseModel):
    """Pagination settings."""

    max_total_hits: int = Field(default=1000, alias="maxTotalHits")

    model_config = {"populate_by_name": True}


class IndexSettings(BaseModel):
    """Complete settings for a MeiliSearch index."""

    displayed_attributes: list[str] = Field(
        default_factory=lambda: ["*"], alias="displayedAttributes"
    )
    searchable_attributes: list[str] = Field(
        default_factory=lambda: ["*"], alias="searchableAttributes"
    )
    filterable_attributes: list[str] = Field(
        default_factory=list, alias="filterableAttributes"
    )
    sortable_attributes: list[str] = Field(
        default_factory=list, alias="sortableAttributes"
    )
    ranking_rules: list[str] = Field(
        default_factory=lambda: [
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness",
        ],
        alias="rankingRules",
    )
    stop_words: list[str] = Field(default_factory=list, alias="stopWords")
    synonyms: dict[str, list[str]] = Field(default_factory=dict)
    distinct_attribute: str | None = Field(default=None, alias="distinctAttribute")
    typo_tolerance: TypoToleranceSettings = Field(
        default_factory=TypoToleranceSettings, alias="typoTolerance"
    )
    faceting: FacetingSettings = Field(default_factory=FacetingSettings)
    pagination: PaginationSettings = Field(default_factory=PaginationSettings)
    proximity_precision: str = Field(default="byWord", alias="proximityPrecision")
    separator_tokens: list[str] = Field(default_factory=list, alias="separatorTokens")
    non_separator_tokens: list[str] = Field(
        default_factory=list, alias="nonSeparatorTokens"
    )
    dictionary: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class IndexStats(BaseModel):
    """Statistics for a MeiliSearch index."""

    number_of_documents: int = Field(default=0, alias="numberOfDocuments")
    is_indexing: bool = Field(default=False, alias="isIndexing")
    field_distribution: dict[str, int] = Field(
        default_factory=dict, alias="fieldDistribution"
    )

    model_config = {"populate_by_name": True}


class IndexData(BaseModel):
    """Complete data for a MeiliSearch index."""

    uid: str = Field(..., description="Index unique identifier")
    primary_key: str | None = Field(default=None, alias="primaryKey")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    settings: IndexSettings = Field(default_factory=IndexSettings)
    stats: IndexStats = Field(default_factory=IndexStats)
    sample_documents: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @property
    def document_count(self) -> int:
        """Get the document count from stats."""
        return self.stats.number_of_documents

    @property
    def field_count(self) -> int:
        """Get the unique field count from stats."""
        return len(self.stats.field_distribution)
