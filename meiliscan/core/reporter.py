"""Reporter for generating analysis reports."""

import asyncio
from datetime import datetime
from typing import Any

from meiliscan.core.analyzer import Analyzer
from meiliscan.core.collector import DataCollector
from meiliscan.core.progress import ProgressCallback, emit_analyze
from meiliscan.core.statistics import calculate_statistics
from meiliscan.models.finding import Finding, FindingSeverity
from meiliscan.models.index import IndexData
from meiliscan.models.report import ActionPlan, AnalysisReport, SourceInfo
from meiliscan.models.statistics import CollectionTiming

# Default concurrency for parallel analysis
DEFAULT_MAX_CONCURRENT = 10


class Reporter:
    """Generate analysis reports from collected data."""

    def __init__(
        self,
        collector: DataCollector,
        analyzer: Analyzer | None = None,
        analysis_options: dict[str, Any] | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        """Initialize the reporter.

        Args:
            collector: Data collector with collected data
            analyzer: Optional analyzer instance
            analysis_options: Optional analysis configuration containing:
                - config_toml: InstanceLaunchConfig for instance config analysis
                - probe_search: Whether search probes were run
                - _probe_findings: List of findings from search probes
                - detect_sensitive: Whether to detect PII fields
            max_concurrent: Maximum number of indexes to analyze concurrently
        """
        self._collector = collector
        self._analyzer = analyzer or Analyzer()
        self._analysis_options = analysis_options or {}
        self._max_concurrent = max_concurrent

    async def generate_report(
        self,
        source_url: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> AnalysisReport:
        """Generate a complete analysis report.

        Args:
            source_url: URL of the MeiliSearch instance
            progress_cb: Optional callback for progress updates

        Returns:
            Complete analysis report
        """
        # Create report with source info
        report = AnalysisReport(
            source=SourceInfo(
                type="instance",
                url=source_url,
                meilisearch_version=self._collector.version,
            ),
            generated_at=datetime.utcnow(),
        )

        # Add global stats
        global_stats = self._collector.global_stats
        if global_stats:
            report.summary.database_size_bytes = global_stats.get("databaseSize")

        # Process each index in parallel
        indexes = self._collector.indexes
        total_indexes = len(indexes)
        detect_sensitive = self._analysis_options.get("detect_sensitive", False)

        emit_analyze(
            progress_cb,
            f"Analyzing {total_indexes} indexes...",
            current=0,
            total=total_indexes,
        )

        # Analyze indexes concurrently
        index_results = await self._analyze_indexes_parallel(
            indexes, detect_sensitive, total_indexes, progress_cb
        )

        # Add results to report (must be done sequentially to maintain order)
        for index, findings in index_results:
            report.add_index(index)
            for finding in findings:
                report.add_finding(finding)

        # Run global analysis
        emit_analyze(
            progress_cb,
            "Running global checks...",
            current=total_indexes,
            total=total_indexes,
        )
        global_findings = await self._analyzer.analyze_global(
            indexes=self._collector.indexes,
            global_stats=self._collector.global_stats,
            tasks=self._collector.tasks,
            instance_version=self._collector.version,
            instance_config=self._analysis_options.get("config_toml"),
        )
        for finding in global_findings:
            report.add_finding(finding)

        # Add probe findings if any
        probe_findings = self._analysis_options.get("_probe_findings", [])
        for finding in probe_findings:
            report.add_finding(finding)

        # Calculate summary
        emit_analyze(
            progress_cb,
            "Calculating statistics...",
            current=total_indexes,
            total=total_indexes,
        )
        report.calculate_summary()

        # Calculate statistics (replaces health_score)
        collection_timing = self._get_collection_timing()
        database_size = global_stats.get("databaseSize") if global_stats else None
        used_size = global_stats.get("usedDatabaseSize") if global_stats else None

        # Get tasks for throughput calculation
        tasks = self._collector.tasks if hasattr(self._collector, "tasks") else None

        report.statistics = calculate_statistics(
            report,
            collection_timing=collection_timing,
            database_size_bytes=database_size,
            used_size_bytes=used_size,
            tasks=tasks,
            benchmark=report.benchmark,
        )

        # Run connection diagnostics if live instance
        connection_diagnostics = await self._run_connection_diagnostics()
        if connection_diagnostics and report.statistics:
            report.statistics.connection_diagnostics = connection_diagnostics

        # Run post-statistics findings (connection diagnostics + throughput)
        from meiliscan.analyzers.performance_analyzer import PerformanceAnalyzer

        post_analyzer = PerformanceAnalyzer()
        post_findings = post_analyzer._check_network_overhead(connection_diagnostics)
        post_findings.extend(
            post_analyzer._check_connection_jitter(connection_diagnostics)
        )
        throughput = report.statistics.throughput if report.statistics else None
        post_findings.extend(
            post_analyzer._check_low_throughput(throughput, self._collector.indexes)
        )
        for finding in post_findings:
            report.add_finding(finding)

        # Recalculate summary after adding post-statistics findings
        if post_findings:
            report._invalidate_cache()
            report.calculate_summary()

        # Generate action plan
        report.action_plan = self._generate_action_plan(report)

        emit_analyze(
            progress_cb,
            f"Analysis complete: {report.finding_count} findings",
            current=total_indexes,
            total=total_indexes,
        )

        return report

    def _get_collection_timing(self) -> CollectionTiming | None:
        """Get collection timing from the collector if available."""
        # Try to get timing from live instance collector
        if hasattr(self._collector, "_instance_collector"):
            instance_collector = self._collector._instance_collector
            if hasattr(instance_collector, "timing"):
                return instance_collector.timing
        return None

    async def _run_connection_diagnostics(self):
        """Run connection diagnostics if connected to a live instance."""
        from meiliscan.collectors.live_instance import LiveInstanceCollector

        if hasattr(self._collector, "_instance_collector"):
            instance_collector = self._collector._instance_collector
            if isinstance(instance_collector, LiveInstanceCollector):
                try:
                    return await instance_collector.diagnose_connection()
                except Exception:
                    return None
        # Also check _collector directly
        if hasattr(self._collector, "_collector"):
            collector = self._collector._collector
            if isinstance(collector, LiveInstanceCollector):
                try:
                    return await collector.diagnose_connection()
                except Exception:
                    return None
        return None

    async def _analyze_indexes_parallel(
        self,
        indexes: list[IndexData],
        detect_sensitive: bool,
        total_indexes: int,
        progress_cb: ProgressCallback | None,
    ) -> list[tuple[IndexData, list[Finding]]]:
        """Analyze multiple indexes in parallel.

        Args:
            indexes: List of indexes to analyze
            detect_sensitive: Whether to detect PII/sensitive fields
            total_indexes: Total number of indexes for progress reporting
            progress_cb: Optional callback for progress updates

        Returns:
            List of (index, findings) tuples in original order
        """
        if not indexes:
            return []

        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self._max_concurrent)
        completed_count = 0
        completed_lock = asyncio.Lock()

        async def analyze_single(
            index: IndexData, index_num: int
        ) -> tuple[IndexData, list[Finding]]:
            nonlocal completed_count

            async with semaphore:
                emit_analyze(
                    progress_cb,
                    f"Analyzing index: {index.uid}",
                    current=completed_count,
                    total=total_indexes,
                    index_uid=index.uid,
                )

                # Run analysis (async)
                findings = await self._analyzer.analyze_index(
                    index, detect_sensitive=detect_sensitive
                )

                async with completed_lock:
                    completed_count += 1
                    emit_analyze(
                        progress_cb,
                        f"Analyzed {index.uid} ({completed_count}/{total_indexes})",
                        current=completed_count,
                        total=total_indexes,
                        index_uid=index.uid,
                    )

                return (index, findings)

        # Create tasks for all indexes
        tasks = [analyze_single(index, i) for i, index in enumerate(indexes, start=1)]

        # Run all tasks concurrently and gather results
        results = await asyncio.gather(*tasks)

        return list(results)

    def _generate_action_plan(self, report: AnalysisReport) -> ActionPlan:
        """Generate prioritized action plan from findings.

        Args:
            report: The analysis report

        Returns:
            Action plan with prioritized findings
        """
        all_findings = report.get_all_findings()

        # Sort findings by severity (critical first)
        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
            FindingSeverity.INFO: 3,
        }

        sorted_findings = sorted(
            all_findings,
            key=lambda f: (severity_order.get(f.severity, 4), f.id),
        )

        priority_order = [
            f.id for f in sorted_findings if f.severity != FindingSeverity.INFO
        ]

        # Estimate impact based on findings
        estimated_impact = {}
        critical_count = report.summary.critical_issues
        warning_count = report.summary.warnings

        if critical_count > 0:
            estimated_impact["index_size_reduction"] = "~20-40%"
            estimated_impact["indexing_speed_improvement"] = "~15-30%"

        if warning_count > 0:
            estimated_impact["search_latency_improvement"] = "~5-15%"

        return ActionPlan(
            priority_order=priority_order,
            estimated_impact=estimated_impact,
        )
