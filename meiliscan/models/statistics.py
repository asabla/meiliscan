"""Statistics models for analysis insights."""

from typing import Literal

from pydantic import BaseModel, Field


class CollectionTiming(BaseModel):
    """Timing metrics from data collection."""

    connect_ms: float = Field(
        default=0.0, description="Time to connect and verify health"
    )
    version_ms: float = Field(default=0.0, description="Time to fetch version info")
    stats_ms: float = Field(default=0.0, description="Time to fetch global stats")
    indexes_list_ms: float = Field(default=0.0, description="Time to list all indexes")
    per_index_avg_ms: float = Field(
        default=0.0, description="Average time per index fetch"
    )
    total_ms: float = Field(default=0.0, description="Total collection time")

    def to_display_dict(self) -> dict[str, str]:
        """Convert to display-friendly format with units."""
        return {
            "connect": f"{self.connect_ms:.0f}ms",
            "version": f"{self.version_ms:.0f}ms",
            "stats": f"{self.stats_ms:.0f}ms",
            "indexes_list": f"{self.indexes_list_ms:.0f}ms",
            "per_index_avg": f"{self.per_index_avg_ms:.0f}ms",
            "total": f"{self.total_ms:.0f}ms",
        }


class IndexStatistics(BaseModel):
    """Statistics for a single index."""

    uid: str = Field(..., description="Index unique identifier")
    document_count: int = Field(default=0, description="Number of documents")
    field_count: int = Field(default=0, description="Number of fields")
    size_bytes: int | None = Field(default=None, description="Index size in bytes")

    # Configuration coverage flags
    has_custom_searchable: bool = Field(
        default=False, description="Has non-wildcard searchableAttributes"
    )
    has_custom_filterable: bool = Field(
        default=False, description="Has filterableAttributes configured"
    )
    has_custom_sortable: bool = Field(
        default=False, description="Has sortableAttributes configured"
    )
    has_custom_ranking: bool = Field(
        default=False, description="Has custom ranking rules"
    )
    has_stop_words: bool = Field(default=False, description="Has stop words configured")
    has_synonyms: bool = Field(default=False, description="Has synonyms configured")
    has_typo_config: bool = Field(
        default=False, description="Has custom typo tolerance settings"
    )
    has_distinct: bool = Field(
        default=False, description="Has distinct attribute configured"
    )

    # Calculated coverage percentage
    configuration_coverage: int = Field(
        default=0, description="Percentage of settings customized (0-100)"
    )

    # Issue counts by severity
    critical_count: int = Field(default=0, description="Number of critical issues")
    warning_count: int = Field(default=0, description="Number of warnings")
    suggestion_count: int = Field(default=0, description="Number of suggestions")
    info_count: int = Field(default=0, description="Number of info items")

    @property
    def total_issues(self) -> int:
        """Total number of issues (excluding info)."""
        return self.critical_count + self.warning_count + self.suggestion_count

    @property
    def has_issues(self) -> bool:
        """Whether the index has any critical or warning issues."""
        return self.critical_count > 0 or self.warning_count > 0


class PerformanceOpportunity(BaseModel):
    """A performance improvement opportunity identified from findings."""

    id: str = Field(..., description="Finding ID this opportunity relates to")
    category: str = Field(..., description="Category (schema, documents, performance)")
    title: str = Field(..., description="Short title of the opportunity")
    description: str = Field(..., description="Detailed description")
    estimated_impact: Literal["high", "medium", "low"] = Field(
        ..., description="Estimated impact level"
    )
    affected_indexes: list[str] = Field(
        default_factory=list, description="List of affected index UIDs"
    )
    estimated_improvement: str = Field(
        ..., description="Human-readable improvement estimate"
    )

    @property
    def impact_order(self) -> int:
        """Numeric order for sorting (lower = higher priority)."""
        return {"high": 0, "medium": 1, "low": 2}.get(self.estimated_impact, 3)


class InstanceStatistics(BaseModel):
    """Overall statistics for a MeiliSearch instance."""

    # Resource usage
    total_indexes: int = Field(default=0, description="Total number of indexes")
    total_documents: int = Field(default=0, description="Total document count")
    total_fields: int = Field(
        default=0, description="Total unique fields across indexes"
    )
    database_size_bytes: int | None = Field(
        default=None, description="Total database size in bytes"
    )
    used_size_bytes: int | None = Field(
        default=None, description="Used database size in bytes"
    )
    fragmentation_percent: float | None = Field(
        default=None, description="Database fragmentation percentage"
    )

    # Configuration coverage counts
    indexes_with_custom_searchable: int = Field(
        default=0, description="Indexes with custom searchableAttributes"
    )
    indexes_with_custom_filterable: int = Field(
        default=0, description="Indexes with filterableAttributes"
    )
    indexes_with_custom_sortable: int = Field(
        default=0, description="Indexes with sortableAttributes"
    )
    indexes_with_custom_ranking: int = Field(
        default=0, description="Indexes with custom ranking rules"
    )
    indexes_with_stop_words: int = Field(
        default=0, description="Indexes with stop words"
    )
    indexes_with_synonyms: int = Field(default=0, description="Indexes with synonyms")

    # Overall coverage percentage
    overall_coverage_percent: int = Field(
        default=0, description="Average configuration coverage across all indexes"
    )

    # Collection timing
    collection_timing: CollectionTiming | None = Field(
        default=None, description="Timing metrics from data collection"
    )

    # Per-index breakdown
    index_statistics: list[IndexStatistics] = Field(
        default_factory=list, description="Statistics for each index"
    )

    # Performance opportunities
    performance_opportunities: list[PerformanceOpportunity] = Field(
        default_factory=list,
        description="Identified performance improvement opportunities",
    )

    # Issue totals
    total_critical: int = Field(default=0, description="Total critical issues")
    total_warnings: int = Field(default=0, description="Total warnings")
    total_suggestions: int = Field(default=0, description="Total suggestions")
    total_info: int = Field(default=0, description="Total info items")

    @property
    def high_impact_opportunities(self) -> list[PerformanceOpportunity]:
        """Get high impact opportunities."""
        return [
            o for o in self.performance_opportunities if o.estimated_impact == "high"
        ]

    @property
    def medium_impact_opportunities(self) -> list[PerformanceOpportunity]:
        """Get medium impact opportunities."""
        return [
            o for o in self.performance_opportunities if o.estimated_impact == "medium"
        ]

    @property
    def low_impact_opportunities(self) -> list[PerformanceOpportunity]:
        """Get low impact opportunities."""
        return [
            o for o in self.performance_opportunities if o.estimated_impact == "low"
        ]

    def get_coverage_summary(self) -> dict[str, str]:
        """Get a summary of configuration coverage."""
        if self.total_indexes == 0:
            return {}

        return {
            "searchable": f"{self.indexes_with_custom_searchable}/{self.total_indexes}",
            "filterable": f"{self.indexes_with_custom_filterable}/{self.total_indexes}",
            "sortable": f"{self.indexes_with_custom_sortable}/{self.total_indexes}",
            "ranking": f"{self.indexes_with_custom_ranking}/{self.total_indexes}",
            "stop_words": f"{self.indexes_with_stop_words}/{self.total_indexes}",
            "synonyms": f"{self.indexes_with_synonyms}/{self.total_indexes}",
        }
