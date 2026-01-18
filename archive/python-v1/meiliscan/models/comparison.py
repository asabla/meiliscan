"""Models for historical comparison between analysis reports."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from meiliscan.models.finding import Finding, FindingSeverity


class ChangeType(str, Enum):
    """Type of change detected between reports."""

    ADDED = "added"
    REMOVED = "removed"
    IMPROVED = "improved"
    DEGRADED = "degraded"
    UNCHANGED = "unchanged"


class TrendDirection(str, Enum):
    """Direction of a metric trend."""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class MetricChange(BaseModel):
    """Represents a change in a numeric metric."""

    name: str = Field(..., description="Metric name")
    old_value: int | float | None = Field(default=None, description="Previous value")
    new_value: int | float | None = Field(default=None, description="Current value")
    change: int | float = Field(default=0, description="Absolute change")
    change_percent: float | None = Field(default=None, description="Percentage change")
    trend: TrendDirection = Field(default=TrendDirection.STABLE)

    @classmethod
    def calculate(
        cls,
        name: str,
        old_value: int | float | None,
        new_value: int | float | None,
        higher_is_better: bool = True,
    ) -> "MetricChange":
        """Calculate metric change between two values.

        Args:
            name: Metric name
            old_value: Previous value
            new_value: Current value
            higher_is_better: Whether increasing values are positive

        Returns:
            MetricChange instance with calculated fields
        """
        if old_value is None or new_value is None:
            return cls(name=name, old_value=old_value, new_value=new_value)

        change = new_value - old_value
        change_percent = (change / old_value * 100) if old_value != 0 else None

        if change > 0:
            trend = TrendDirection.UP
        elif change < 0:
            trend = TrendDirection.DOWN
        else:
            trend = TrendDirection.STABLE

        return cls(
            name=name,
            old_value=old_value,
            new_value=new_value,
            change=change,
            change_percent=change_percent,
            trend=trend,
        )


class FindingChange(BaseModel):
    """Represents a change in a finding between reports."""

    finding: Finding = Field(..., description="The finding that changed")
    change_type: ChangeType = Field(..., description="Type of change")
    previous_severity: FindingSeverity | None = Field(
        default=None, description="Previous severity (if changed)"
    )


class IndexChange(BaseModel):
    """Changes detected for a specific index."""

    uid: str = Field(..., description="Index UID")
    change_type: ChangeType = Field(..., description="Overall change type")
    document_count: MetricChange | None = Field(default=None)
    field_count: MetricChange | None = Field(default=None)
    finding_count: MetricChange | None = Field(default=None)
    new_findings: list[Finding] = Field(default_factory=list)
    resolved_findings: list[Finding] = Field(default_factory=list)
    settings_changed: bool = Field(default=False)
    settings_diff: dict[str, Any] = Field(default_factory=dict)


class ComparisonSummary(BaseModel):
    """Summary of comparison between two reports."""

    old_report_date: datetime = Field(..., description="Date of older report")
    new_report_date: datetime = Field(..., description="Date of newer report")
    time_between: str = Field(..., description="Human-readable time difference")

    # Index changes
    indexes_added: list[str] = Field(default_factory=list)
    indexes_removed: list[str] = Field(default_factory=list)
    indexes_changed: list[str] = Field(default_factory=list)

    # Metric changes
    health_score: MetricChange = Field(...)
    total_documents: MetricChange = Field(...)
    total_indexes: MetricChange = Field(...)
    critical_issues: MetricChange = Field(...)
    warnings: MetricChange = Field(...)
    suggestions: MetricChange = Field(...)

    # Overall assessment
    overall_trend: TrendDirection = Field(default=TrendDirection.STABLE)
    improvement_areas: list[str] = Field(default_factory=list)
    degradation_areas: list[str] = Field(default_factory=list)


class ComparisonReport(BaseModel):
    """Complete comparison between two analysis reports."""

    version: str = Field(default="1.0.0")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Source reports
    old_source: dict[str, Any] = Field(..., description="Old report source info")
    new_source: dict[str, Any] = Field(..., description="New report source info")

    # Summary
    summary: ComparisonSummary = Field(...)

    # Detailed changes
    index_changes: dict[str, IndexChange] = Field(default_factory=dict)
    finding_changes: list[FindingChange] = Field(default_factory=list)

    # Recommendations based on trends
    recommendations: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for export."""
        return self.model_dump(mode="json", exclude_none=True)
