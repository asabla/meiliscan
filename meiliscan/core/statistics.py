"""Statistics calculator for generating instance statistics from analysis data."""

import re

from meiliscan.models.benchmark import BenchmarkReport
from meiliscan.models.finding import Finding, FindingSeverity
from meiliscan.models.index import IndexSettings
from meiliscan.models.report import AnalysisReport, IndexAnalysis
from meiliscan.models.statistics import (
    CollectionTiming,
    IndexStatistics,
    InstanceStatistics,
    PerformanceOpportunity,
    ThroughputMetrics,
)

# Default ranking rules for comparison
DEFAULT_RANKING_RULES = [
    "words",
    "typo",
    "proximity",
    "attribute",
    "sort",
    "exactness",
]

# Mapping of finding IDs to performance impact estimates
FINDING_IMPACT_MAP: dict[str, dict] = {
    # Schema findings - high impact
    "MEILI-S001": {
        "impact": "high",
        "improvement": "Reduce index size by ~30-50%, faster indexing and search",
    },
    "MEILI-S002": {
        "impact": "medium",
        "improvement": "Enable filtering capabilities for better query precision",
    },
    "MEILI-S003": {
        "impact": "medium",
        "improvement": "Enable sorting capabilities for result ordering",
    },
    "MEILI-S004": {
        "impact": "low",
        "improvement": "Customize ranking for better relevance",
    },
    "MEILI-S005": {
        "impact": "medium",
        "improvement": "Reduce index size ~10-15%, improve relevance for common words",
    },
    "MEILI-S006": {
        "impact": "low",
        "improvement": "Improve search quality with synonym expansion",
    },
    "MEILI-S007": {
        "impact": "low",
        "improvement": "Enable result deduplication",
    },
    "MEILI-S008": {
        "impact": "low",
        "improvement": "Optimize search precision for specific attributes",
    },
    "MEILI-S009": {
        "impact": "low",
        "improvement": "Optimize search precision for specific attributes",
    },
    "MEILI-S010": {
        "impact": "medium",
        "improvement": "Enable geo-based filtering and sorting",
    },
    # Document findings
    "MEILI-D001": {
        "impact": "high",
        "improvement": "Reduce memory usage and improve consistency",
    },
    "MEILI-D002": {
        "impact": "medium",
        "improvement": "Reduce storage and improve query performance",
    },
    "MEILI-D003": {
        "impact": "medium",
        "improvement": "Improve search accuracy with schema validation",
    },
    "MEILI-D004": {
        "impact": "low",
        "improvement": "Improve data quality and completeness",
    },
    "MEILI-D005": {
        "impact": "medium",
        "improvement": "Reduce PII exposure risk",
    },
    "MEILI-D006": {
        "impact": "medium",
        "improvement": "Simplify queries and improve performance",
    },
    "MEILI-D007": {
        "impact": "low",
        "improvement": "Enable date-based filtering and sorting",
    },
    "MEILI-D008": {
        "impact": "low",
        "improvement": "Enable geo-based filtering",
    },
    # Performance findings - high impact
    "MEILI-P001": {
        "impact": "high",
        "improvement": "Reduce indexing complexity and memory usage",
    },
    "MEILI-P002": {
        "impact": "high",
        "improvement": "Improve indexing success rate",
    },
    "MEILI-P003": {
        "impact": "medium",
        "improvement": "Improve indexing throughput",
    },
    "MEILI-P004": {
        "impact": "medium",
        "improvement": "Reclaim disk space",
    },
    "MEILI-P005": {
        "impact": "medium",
        "improvement": "Improve indexing efficiency",
    },
    "MEILI-P006": {
        "impact": "low",
        "improvement": "Simplify instance management",
    },
    "MEILI-P011": {
        "impact": "medium",
        "improvement": "Reduce network overhead for faster search responses",
    },
    "MEILI-P012": {
        "impact": "medium",
        "improvement": "Stabilize connection latency for predictable search times",
    },
    "MEILI-P013": {
        "impact": "medium",
        "improvement": "Improve indexing throughput for faster data updates",
    },
    # Search probe findings
    "MEILI-Q004": {
        "impact": "medium",
        "improvement": "Reduce memory usage from high-cardinality facets",
    },
    "MEILI-Q005": {
        "impact": "low",
        "improvement": "Review skewed facet utility",
    },
    "MEILI-Q007": {
        "impact": "medium",
        "improvement": "Ensure typo tolerance works for common search terms",
    },
    # Best practices
    "MEILI-B001": {
        "impact": "low",
        "improvement": "Optimize filtering by removing searchable overlap",
    },
    "MEILI-B002": {
        "impact": "medium",
        "improvement": "Ensure consistent search behavior",
    },
    "MEILI-B003": {
        "impact": "low",
        "improvement": "Enable semantic search capabilities",
    },
    "MEILI-B004": {
        "impact": "medium",
        "improvement": "Access latest features and security fixes",
    },
}


def calculate_configuration_coverage(
    settings: IndexSettings,
) -> tuple[dict[str, bool], int]:
    """Calculate configuration coverage for index settings.

    Args:
        settings: The index settings to analyze

    Returns:
        Tuple of (coverage flags dict, coverage percentage)
    """
    flags = {
        "has_custom_searchable": settings.searchable_attributes != ["*"],
        "has_custom_filterable": len(settings.filterable_attributes) > 0,
        "has_custom_sortable": len(settings.sortable_attributes) > 0,
        "has_custom_ranking": settings.ranking_rules != DEFAULT_RANKING_RULES,
        "has_stop_words": len(settings.stop_words) > 0,
        "has_synonyms": len(settings.synonyms) > 0,
        "has_typo_config": (
            not settings.typo_tolerance.enabled
            or len(settings.typo_tolerance.disable_on_words) > 0
            or len(settings.typo_tolerance.disable_on_attributes) > 0
        ),
        "has_distinct": settings.distinct_attribute is not None,
    }

    # Calculate percentage (each flag is worth equal weight)
    configured_count = sum(1 for v in flags.values() if v)
    total_settings = len(flags)
    coverage_percent = int((configured_count / total_settings) * 100)

    return flags, coverage_percent


def calculate_index_statistics(
    index_uid: str, index_analysis: IndexAnalysis
) -> IndexStatistics:
    """Calculate statistics for a single index.

    Args:
        index_uid: The index UID
        index_analysis: The index analysis data

    Returns:
        IndexStatistics for the index
    """
    # Get settings from the analysis
    current_settings = index_analysis.settings.get("current", {})

    # Build IndexSettings from the dict
    settings = (
        IndexSettings(**current_settings) if current_settings else IndexSettings()
    )

    # Calculate configuration coverage
    coverage_flags, coverage_percent = calculate_configuration_coverage(settings)

    # Count findings by severity
    severity_counts = {
        "critical": 0,
        "warning": 0,
        "suggestion": 0,
        "info": 0,
    }
    for finding in index_analysis.findings:
        severity_key = finding.severity.value.lower()
        if severity_key in severity_counts:
            severity_counts[severity_key] += 1

    return IndexStatistics(
        uid=index_uid,
        document_count=index_analysis.metadata.get("document_count", 0),
        field_count=index_analysis.statistics.get("field_count", 0),
        size_bytes=None,  # Not available per-index from MeiliSearch API
        has_custom_searchable=coverage_flags["has_custom_searchable"],
        has_custom_filterable=coverage_flags["has_custom_filterable"],
        has_custom_sortable=coverage_flags["has_custom_sortable"],
        has_custom_ranking=coverage_flags["has_custom_ranking"],
        has_stop_words=coverage_flags["has_stop_words"],
        has_synonyms=coverage_flags["has_synonyms"],
        has_typo_config=coverage_flags["has_typo_config"],
        has_distinct=coverage_flags["has_distinct"],
        configuration_coverage=coverage_percent,
        critical_count=severity_counts["critical"],
        warning_count=severity_counts["warning"],
        suggestion_count=severity_counts["suggestion"],
        info_count=severity_counts["info"],
    )


def identify_performance_opportunities(
    findings: list[Finding],
) -> list[PerformanceOpportunity]:
    """Identify performance improvement opportunities from findings.

    Groups findings by ID and creates opportunities with affected indexes.

    Args:
        findings: List of all findings

    Returns:
        List of PerformanceOpportunity objects sorted by impact
    """
    # Group findings by ID
    findings_by_id: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.id not in findings_by_id:
            findings_by_id[finding.id] = []
        findings_by_id[finding.id].append(finding)

    opportunities: list[PerformanceOpportunity] = []

    for finding_id, grouped_findings in findings_by_id.items():
        # Skip INFO severity findings for performance opportunities
        if all(f.severity == FindingSeverity.INFO for f in grouped_findings):
            continue

        # Get impact info from map, or use defaults based on severity
        impact_info = FINDING_IMPACT_MAP.get(finding_id)
        if impact_info:
            impact = impact_info["impact"]
            improvement = impact_info["improvement"]
        else:
            # Default impact based on highest severity in group
            max_severity = max(
                grouped_findings, key=lambda f: _severity_order(f.severity)
            )
            if max_severity.severity == FindingSeverity.CRITICAL:
                impact = "high"
            elif max_severity.severity == FindingSeverity.WARNING:
                impact = "medium"
            else:
                impact = "low"
            improvement = "Resolve this finding to improve search quality"

        # Get representative finding for title/description
        representative = grouped_findings[0]

        # Collect affected indexes
        affected_indexes = sorted(
            set(f.index_uid for f in grouped_findings if f.index_uid)
        )

        opportunities.append(
            PerformanceOpportunity(
                id=finding_id,
                category=representative.category.value,
                title=representative.title,
                description=representative.description,
                estimated_impact=impact,  # type: ignore
                affected_indexes=affected_indexes,
                estimated_improvement=improvement,
            )
        )

    # Sort by impact (high first, then medium, then low)
    opportunities.sort(key=lambda o: o.impact_order)

    return opportunities


def _severity_order(severity: FindingSeverity) -> int:
    """Get numeric order for severity (higher = more severe)."""
    return {
        FindingSeverity.INFO: 0,
        FindingSeverity.SUGGESTION: 1,
        FindingSeverity.WARNING: 2,
        FindingSeverity.CRITICAL: 3,
    }.get(severity, 0)


def calculate_health_score(
    configuration_coverage: int,
    critical_count: int,
    warning_count: int,
    p95_latency_ms: float | None,
    task_failure_rate: float | None,
) -> int:
    """Calculate composite health score (0-100).

    Scoring formula (weighted):
    - Configuration coverage: 30 points (proportional to coverage)
    - No critical issues: 25 points (0 if any critical, 25 if none)
    - Low warnings: 15 points (proportional: 0 warnings = 15, 5+ = 0)
    - Search performance: 15 points (based on p95 latency)
    - No task failures: 15 points (proportional to inverse of failure rate)
    """
    score = 0

    # Configuration coverage: 30 points
    score += int(30 * configuration_coverage / 100)

    # No critical issues: 25 points
    if critical_count == 0:
        score += 25

    # Low warnings: 15 points (0 warnings = 15, 5+ = 0)
    if warning_count == 0:
        score += 15
    elif warning_count < 5:
        score += int(15 * (5 - warning_count) / 5)

    # Search performance: 15 points (based on p95 latency)
    if p95_latency_ms is not None:
        if p95_latency_ms < 50:
            score += 15
        elif p95_latency_ms < 200:
            score += 10
        elif p95_latency_ms < 500:
            score += 5

    # No task failures: 15 points
    if task_failure_rate is not None:
        if task_failure_rate <= 0:
            score += 15
        elif task_failure_rate < 0.1:
            score += int(15 * (1 - task_failure_rate / 0.1))

    return min(score, 100)


def calculate_throughput_metrics(tasks: list[dict] | None) -> ThroughputMetrics | None:
    """Compute indexing throughput from task history.

    Args:
        tasks: List of task dictionaries from MeiliSearch

    Returns:
        ThroughputMetrics or None if insufficient data
    """
    if not tasks:
        return None

    # Filter succeeded document addition tasks with duration and document count
    indexing_tasks = []
    for task in tasks:
        if (
            task.get("type") != "documentAdditionOrUpdate"
            or task.get("status") != "succeeded"
        ):
            continue

        details = task.get("details", {})
        doc_count = details.get("receivedDocuments") or details.get(
            "indexedDocuments", 0
        )
        if not isinstance(doc_count, int) or doc_count <= 0:
            continue

        duration = task.get("duration")
        duration_seconds = None
        if isinstance(duration, str):
            match = re.search(r"PT(?:(\d+)M)?(\d+\.?\d*)S", duration)
            if match:
                minutes = int(match.group(1) or 0)
                seconds = float(match.group(2))
                duration_seconds = minutes * 60 + seconds
        elif isinstance(duration, (int, float)):
            duration_seconds = float(duration)

        if duration_seconds and duration_seconds > 0:
            indexing_tasks.append(
                {
                    "doc_count": doc_count,
                    "duration_seconds": duration_seconds,
                    "docs_per_second": doc_count / duration_seconds,
                    "enqueued_at": task.get("enqueuedAt"),
                }
            )

    if not indexing_tasks:
        return None

    total_docs = sum(t["doc_count"] for t in indexing_tasks)
    total_duration = sum(t["duration_seconds"] for t in indexing_tasks)
    avg_dps = total_docs / total_duration if total_duration > 0 else 0.0
    peak_dps = max(t["docs_per_second"] for t in indexing_tasks)
    avg_batch = total_docs / len(indexing_tasks)

    # Estimate time period from earliest to latest task
    time_period_hours = total_duration / 3600

    return ThroughputMetrics(
        avg_docs_per_second=round(avg_dps, 2),
        peak_docs_per_second=round(peak_dps, 2),
        avg_batch_size=round(avg_batch, 1),
        total_docs_indexed=total_docs,
        time_period_hours=round(time_period_hours, 2),
    )


def calculate_statistics(
    report: AnalysisReport,
    collection_timing: CollectionTiming | None = None,
    database_size_bytes: int | None = None,
    used_size_bytes: int | None = None,
    tasks: list[dict] | None = None,
    benchmark: BenchmarkReport | None = None,
) -> InstanceStatistics:
    """Calculate comprehensive statistics from an analysis report.

    Args:
        report: The analysis report
        collection_timing: Optional timing metrics from data collection
        database_size_bytes: Optional database size in bytes
        used_size_bytes: Optional used database size in bytes
        tasks: Optional task history for throughput calculation
        benchmark: Optional benchmark report for health score calculation

    Returns:
        InstanceStatistics with computed metrics
    """
    # Calculate per-index statistics
    index_stats: list[IndexStatistics] = []
    for index_uid, index_analysis in report.indexes.items():
        idx_stats = calculate_index_statistics(index_uid, index_analysis)
        index_stats.append(idx_stats)

    # Calculate aggregates
    total_documents = sum(idx.document_count for idx in index_stats)
    total_fields = sum(idx.field_count for idx in index_stats)

    # Configuration coverage counts
    indexes_with_custom_searchable = sum(
        1 for idx in index_stats if idx.has_custom_searchable
    )
    indexes_with_custom_filterable = sum(
        1 for idx in index_stats if idx.has_custom_filterable
    )
    indexes_with_custom_sortable = sum(
        1 for idx in index_stats if idx.has_custom_sortable
    )
    indexes_with_custom_ranking = sum(
        1 for idx in index_stats if idx.has_custom_ranking
    )
    indexes_with_stop_words = sum(1 for idx in index_stats if idx.has_stop_words)
    indexes_with_synonyms = sum(1 for idx in index_stats if idx.has_synonyms)

    # Overall coverage percentage (average across all indexes)
    if index_stats:
        overall_coverage = sum(
            idx.configuration_coverage for idx in index_stats
        ) // len(index_stats)
    else:
        overall_coverage = 0

    # Calculate fragmentation if we have size info
    fragmentation_percent = None
    if database_size_bytes and used_size_bytes and database_size_bytes > 0:
        fragmentation_percent = (
            (database_size_bytes - used_size_bytes) / database_size_bytes
        ) * 100

    # Get all findings and calculate totals
    all_findings = report.get_all_findings()
    total_critical = sum(
        1 for f in all_findings if f.severity == FindingSeverity.CRITICAL
    )
    total_warnings = sum(
        1 for f in all_findings if f.severity == FindingSeverity.WARNING
    )
    total_suggestions = sum(
        1 for f in all_findings if f.severity == FindingSeverity.SUGGESTION
    )
    total_info = sum(1 for f in all_findings if f.severity == FindingSeverity.INFO)

    # Identify performance opportunities
    opportunities = identify_performance_opportunities(all_findings)

    # Calculate task failure rate for health score
    task_failure_rate = None
    if tasks and len(tasks) >= 10:
        failed = sum(1 for t in tasks if t.get("status") == "failed")
        task_failure_rate = failed / len(tasks)

    # Get p95 latency from benchmark
    p95_latency = benchmark.p95_latency_ms if benchmark else None

    # Calculate per-index health scores
    for idx in index_stats:
        idx.health_score = calculate_health_score(
            configuration_coverage=idx.configuration_coverage,
            critical_count=idx.critical_count,
            warning_count=idx.warning_count,
            p95_latency_ms=p95_latency,
            task_failure_rate=task_failure_rate,
        )

    # Calculate overall health score
    overall_health = calculate_health_score(
        configuration_coverage=overall_coverage,
        critical_count=total_critical,
        warning_count=total_warnings,
        p95_latency_ms=p95_latency,
        task_failure_rate=task_failure_rate,
    )

    # Calculate throughput metrics
    throughput = calculate_throughput_metrics(tasks)

    return InstanceStatistics(
        total_indexes=len(index_stats),
        total_documents=total_documents,
        total_fields=total_fields,
        database_size_bytes=database_size_bytes,
        used_size_bytes=used_size_bytes,
        fragmentation_percent=fragmentation_percent,
        indexes_with_custom_searchable=indexes_with_custom_searchable,
        indexes_with_custom_filterable=indexes_with_custom_filterable,
        indexes_with_custom_sortable=indexes_with_custom_sortable,
        indexes_with_custom_ranking=indexes_with_custom_ranking,
        indexes_with_stop_words=indexes_with_stop_words,
        indexes_with_synonyms=indexes_with_synonyms,
        overall_coverage_percent=overall_coverage,
        collection_timing=collection_timing,
        index_statistics=index_stats,
        performance_opportunities=opportunities,
        total_critical=total_critical,
        total_warnings=total_warnings,
        total_suggestions=total_suggestions,
        total_info=total_info,
        overall_health_score=overall_health,
        throughput=throughput,
    )
