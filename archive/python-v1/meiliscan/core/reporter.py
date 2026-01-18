"""Reporter for generating analysis reports."""

from typing import Any

from datetime import datetime

from meiliscan.core.analyzer import Analyzer
from meiliscan.core.collector import DataCollector
from meiliscan.core.progress import ProgressCallback, emit_analyze
from meiliscan.core.scorer import HealthScorer
from meiliscan.models.finding import FindingSeverity
from meiliscan.models.report import ActionPlan, AnalysisReport, SourceInfo


class Reporter:
    """Generate analysis reports from collected data."""

    def __init__(
        self,
        collector: DataCollector,
        analyzer: Analyzer | None = None,
        scorer: HealthScorer | None = None,
        analysis_options: dict[str, Any] | None = None,
    ):
        """Initialize the reporter.

        Args:
            collector: Data collector with collected data
            analyzer: Optional analyzer instance
            scorer: Optional health scorer instance
            analysis_options: Optional analysis configuration containing:
                - config_toml: InstanceLaunchConfig for instance config analysis
                - probe_search: Whether search probes were run
                - _probe_findings: List of findings from search probes
                - detect_sensitive: Whether to detect PII fields
        """
        self._collector = collector
        self._analyzer = analyzer or Analyzer()
        self._scorer = scorer or HealthScorer()
        self._analysis_options = analysis_options or {}

    def generate_report(
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

        # Process each index
        indexes = self._collector.indexes
        total_indexes = len(indexes)
        detect_sensitive = self._analysis_options.get("detect_sensitive", False)

        emit_analyze(
            progress_cb,
            f"Analyzing {total_indexes} indexes...",
            current=0,
            total=total_indexes,
        )

        for i, index in enumerate(indexes, start=1):
            emit_analyze(
                progress_cb,
                f"Analyzing index: {index.uid}",
                current=i,
                total=total_indexes,
                index_uid=index.uid,
            )

            report.add_index(index)

            # Run analysis
            findings = self._analyzer.analyze_index(
                index, detect_sensitive=detect_sensitive
            )
            for finding in findings:
                report.add_finding(finding)

        # Run global analysis
        emit_analyze(
            progress_cb,
            "Running global checks...",
            current=total_indexes,
            total=total_indexes,
        )
        global_findings = self._analyzer.analyze_global(
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

        # Calculate summary and score
        emit_analyze(
            progress_cb,
            "Calculating health score...",
            current=total_indexes,
            total=total_indexes,
        )
        report.calculate_summary()
        self._scorer.score_report(report)

        # Generate action plan
        report.action_plan = self._generate_action_plan(report)

        emit_analyze(
            progress_cb,
            f"Analysis complete: {len(report.get_all_findings())} findings",
            current=total_indexes,
            total=total_indexes,
        )

        return report

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
