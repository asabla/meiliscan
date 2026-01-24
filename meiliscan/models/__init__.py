"""Models module initialization."""

from meiliscan.models.benchmark import (
    BenchmarkReport,
    FixBenchmark,
    IndexBenchmark,
    SearchBenchmarkResult,
    SearchQuery,
)
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
from meiliscan.models.statistics import (
    CollectionTiming,
    IndexStatistics,
    InstanceStatistics,
    PerformanceOpportunity,
)
from meiliscan.models.task import (
    Task,
    TaskError,
    TasksResponse,
    TasksSummary,
    TaskStatus,
    TaskType,
)

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
    # Statistics models
    "CollectionTiming",
    "IndexStatistics",
    "InstanceStatistics",
    "PerformanceOpportunity",
    # Benchmark models
    "BenchmarkReport",
    "FixBenchmark",
    "IndexBenchmark",
    "SearchBenchmarkResult",
    "SearchQuery",
    # Comparison models
    "ChangeType",
    "ComparisonReport",
    "ComparisonSummary",
    "FindingChange",
    "IndexChange",
    "MetricChange",
    "TrendDirection",
    # Task models
    "Task",
    "TaskError",
    "TasksResponse",
    "TasksSummary",
    "TaskStatus",
    "TaskType",
]
