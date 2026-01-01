"""Reporter for generating analysis reports."""

from datetime import datetime

from meilisearch_analyzer.core.analyzer import Analyzer
from meilisearch_analyzer.core.collector import DataCollector
from meilisearch_analyzer.core.scorer import HealthScorer
from meilisearch_analyzer.models.finding import Finding, FindingSeverity
from meilisearch_analyzer.models.report import ActionPlan, AnalysisReport, SourceInfo


class Reporter:
    """Generate analysis reports from collected data."""

    def __init__(
        self,
        collector: DataCollector,
        analyzer: Analyzer | None = None,
        scorer: HealthScorer | None = None,
    ):
        """Initialize the reporter.

        Args:
            collector: Data collector with collected data
            analyzer: Optional analyzer instance
            scorer: Optional health scorer instance
        """
        self._collector = collector
        self._analyzer = analyzer or Analyzer()
        self._scorer = scorer or HealthScorer()

    def generate_report(self, source_url: str | None = None) -> AnalysisReport:
        """Generate a complete analysis report.

        Args:
            source_url: URL of the MeiliSearch instance

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
        for index in self._collector.indexes:
            report.add_index(index)

            # Run analysis
            findings = self._analyzer.analyze_index(index)
            for finding in findings:
                report.add_finding(finding)

        # Calculate summary and score
        report.calculate_summary()
        self._scorer.score_report(report)

        # Generate action plan
        report.action_plan = self._generate_action_plan(report)

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

        priority_order = [f.id for f in sorted_findings if f.severity != FindingSeverity.INFO]

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
