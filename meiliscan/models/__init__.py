"""Models module initialization."""

from meiliscan.models.comparison import (
    ChangeType,
    ComparisonReport,
    ComparisonSummary,
    FindingChange,
    IndexChange,
    MetricChange,
    TrendDirection,
)
from meiliscan.models.finding import Finding, FindingCategory, FindingSeverity
from meiliscan.models.index import IndexData, IndexSettings, IndexStats
from meiliscan.models.report import AnalysisReport, AnalysisSummary, SourceInfo

__all__ = [
    # Finding models
    "Finding",
    "FindingSeverity",
    "FindingCategory",
    # Index models
    "IndexData",
    "IndexSettings",
    "IndexStats",
    # Report models
    "AnalysisReport",
    "AnalysisSummary",
    "SourceInfo",
    # Comparison models
    "ChangeType",
    "ComparisonReport",
    "ComparisonSummary",
    "FindingChange",
    "IndexChange",
    "MetricChange",
    "TrendDirection",
]
