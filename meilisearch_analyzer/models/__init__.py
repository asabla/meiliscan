"""Models module initialization."""

from meilisearch_analyzer.models.comparison import (
    ChangeType,
    ComparisonReport,
    ComparisonSummary,
    FindingChange,
    IndexChange,
    MetricChange,
    TrendDirection,
)
from meilisearch_analyzer.models.finding import Finding, FindingCategory, FindingSeverity
from meilisearch_analyzer.models.index import IndexData, IndexSettings, IndexStats
from meilisearch_analyzer.models.report import AnalysisReport, AnalysisSummary, SourceInfo

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
