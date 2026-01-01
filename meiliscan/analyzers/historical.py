"""Historical analyzer for comparing analysis reports over time."""

from datetime import datetime

from meiliscan.models.comparison import (
    ChangeType,
    ComparisonReport,
    ComparisonSummary,
    FindingChange,
    IndexChange,
    MetricChange,
    TrendDirection,
)
from meiliscan.models.report import AnalysisReport


class HistoricalAnalyzer:
    """Analyzer for comparing two analysis reports to detect trends and changes."""

    def compare(
        self,
        old_report: AnalysisReport,
        new_report: AnalysisReport,
    ) -> ComparisonReport:
        """Compare two analysis reports and generate a comparison report.

        Args:
            old_report: The older/baseline report
            new_report: The newer/current report

        Returns:
            ComparisonReport with detailed changes and trends
        """
        # Calculate time between reports
        time_between = self._format_time_difference(
            old_report.generated_at, new_report.generated_at
        )

        # Detect index changes
        old_index_uids = set(old_report.indexes.keys())
        new_index_uids = set(new_report.indexes.keys())

        indexes_added = list(new_index_uids - old_index_uids)
        indexes_removed = list(old_index_uids - new_index_uids)
        common_indexes = old_index_uids & new_index_uids

        # Calculate metric changes
        health_score_change = MetricChange.calculate(
            "health_score",
            old_report.summary.health_score,
            new_report.summary.health_score,
            higher_is_better=True,
        )

        total_documents_change = MetricChange.calculate(
            "total_documents",
            old_report.summary.total_documents,
            new_report.summary.total_documents,
            higher_is_better=True,
        )

        total_indexes_change = MetricChange.calculate(
            "total_indexes",
            old_report.summary.total_indexes,
            new_report.summary.total_indexes,
            higher_is_better=True,
        )

        critical_issues_change = MetricChange.calculate(
            "critical_issues",
            old_report.summary.critical_issues,
            new_report.summary.critical_issues,
            higher_is_better=False,
        )

        warnings_change = MetricChange.calculate(
            "warnings",
            old_report.summary.warnings,
            new_report.summary.warnings,
            higher_is_better=False,
        )

        suggestions_change = MetricChange.calculate(
            "suggestions",
            old_report.summary.suggestions,
            new_report.summary.suggestions,
            higher_is_better=False,
        )

        # Analyze index-level changes
        index_changes: dict[str, IndexChange] = {}
        indexes_changed: list[str] = []

        for uid in common_indexes:
            change = self._compare_index(
                uid,
                old_report.indexes[uid],
                new_report.indexes[uid],
            )
            if change.change_type != ChangeType.UNCHANGED:
                indexes_changed.append(uid)
            index_changes[uid] = change

        # Add entries for new indexes
        for uid in indexes_added:
            new_idx = new_report.indexes[uid]
            index_changes[uid] = IndexChange(
                uid=uid,
                change_type=ChangeType.ADDED,
                document_count=MetricChange(
                    name="document_count",
                    old_value=None,
                    new_value=new_idx.metadata.get("document_count", 0),
                ),
                finding_count=MetricChange(
                    name="finding_count",
                    old_value=None,
                    new_value=len(new_idx.findings),
                ),
                new_findings=new_idx.findings,
            )

        # Add entries for removed indexes
        for uid in indexes_removed:
            old_idx = old_report.indexes[uid]
            index_changes[uid] = IndexChange(
                uid=uid,
                change_type=ChangeType.REMOVED,
                document_count=MetricChange(
                    name="document_count",
                    old_value=old_idx.metadata.get("document_count", 0),
                    new_value=None,
                ),
                finding_count=MetricChange(
                    name="finding_count",
                    old_value=len(old_idx.findings),
                    new_value=None,
                ),
                resolved_findings=old_idx.findings,
            )

        # Analyze finding changes
        finding_changes = self._compare_findings(old_report, new_report)

        # Determine overall trend
        overall_trend = self._determine_overall_trend(
            health_score_change,
            critical_issues_change,
            warnings_change,
        )

        # Generate improvement/degradation areas
        improvement_areas, degradation_areas = self._identify_trend_areas(
            health_score_change,
            critical_issues_change,
            warnings_change,
            suggestions_change,
            total_documents_change,
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            finding_changes,
            index_changes,
            overall_trend,
        )

        summary = ComparisonSummary(
            old_report_date=old_report.generated_at,
            new_report_date=new_report.generated_at,
            time_between=time_between,
            indexes_added=indexes_added,
            indexes_removed=indexes_removed,
            indexes_changed=indexes_changed,
            health_score=health_score_change,
            total_documents=total_documents_change,
            total_indexes=total_indexes_change,
            critical_issues=critical_issues_change,
            warnings=warnings_change,
            suggestions=suggestions_change,
            overall_trend=overall_trend,
            improvement_areas=improvement_areas,
            degradation_areas=degradation_areas,
        )

        return ComparisonReport(
            old_source=old_report.source.model_dump(),
            new_source=new_report.source.model_dump(),
            summary=summary,
            index_changes=index_changes,
            finding_changes=finding_changes,
            recommendations=recommendations,
        )

    def _format_time_difference(self, old_time: datetime, new_time: datetime) -> str:
        """Format the time difference in a human-readable way."""
        diff = new_time - old_time
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60

        if days > 0:
            if days == 1:
                return "1 day"
            return f"{days} days"
        elif hours > 0:
            if hours == 1:
                return "1 hour"
            return f"{hours} hours"
        elif minutes > 0:
            if minutes == 1:
                return "1 minute"
            return f"{minutes} minutes"
        else:
            return "less than a minute"

    def _compare_index(
        self,
        uid: str,
        old_index,
        new_index,
    ) -> IndexChange:
        """Compare two index analyses."""
        old_doc_count = old_index.metadata.get("document_count", 0)
        new_doc_count = new_index.metadata.get("document_count", 0)

        old_field_count = old_index.statistics.get("field_count", 0)
        new_field_count = new_index.statistics.get("field_count", 0)

        old_finding_count = len(old_index.findings)
        new_finding_count = len(new_index.findings)

        # Detect new and resolved findings
        old_finding_ids = {f.id for f in old_index.findings}
        new_finding_ids = {f.id for f in new_index.findings}

        new_findings = [f for f in new_index.findings if f.id not in old_finding_ids]
        resolved_findings = [
            f for f in old_index.findings if f.id not in new_finding_ids
        ]

        # Check settings changes
        old_settings = old_index.settings.get("current", {})
        new_settings = new_index.settings.get("current", {})
        settings_changed = old_settings != new_settings
        settings_diff = (
            self._diff_settings(old_settings, new_settings) if settings_changed else {}
        )

        # Determine change type
        if new_findings or resolved_findings or settings_changed:
            if len(new_findings) > len(resolved_findings):
                change_type = ChangeType.DEGRADED
            elif len(resolved_findings) > len(new_findings):
                change_type = ChangeType.IMPROVED
            else:
                change_type = ChangeType.UNCHANGED
        else:
            change_type = ChangeType.UNCHANGED

        return IndexChange(
            uid=uid,
            change_type=change_type,
            document_count=MetricChange.calculate(
                "document_count", old_doc_count, new_doc_count
            ),
            field_count=MetricChange.calculate(
                "field_count", old_field_count, new_field_count
            ),
            finding_count=MetricChange.calculate(
                "finding_count",
                old_finding_count,
                new_finding_count,
                higher_is_better=False,
            ),
            new_findings=new_findings,
            resolved_findings=resolved_findings,
            settings_changed=settings_changed,
            settings_diff=settings_diff,
        )

    def _diff_settings(self, old: dict, new: dict) -> dict:
        """Create a diff between two settings dictionaries."""
        diff = {}
        all_keys = set(old.keys()) | set(new.keys())

        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}

        return diff

    def _compare_findings(
        self,
        old_report: AnalysisReport,
        new_report: AnalysisReport,
    ) -> list[FindingChange]:
        """Compare findings between two reports."""
        changes: list[FindingChange] = []

        old_findings = {f.id: f for f in old_report.get_all_findings()}
        new_findings = {f.id: f for f in new_report.get_all_findings()}

        # Detect resolved findings
        for fid, finding in old_findings.items():
            if fid not in new_findings:
                changes.append(
                    FindingChange(
                        finding=finding,
                        change_type=ChangeType.REMOVED,
                    )
                )

        # Detect new findings
        for fid, finding in new_findings.items():
            if fid not in old_findings:
                changes.append(
                    FindingChange(
                        finding=finding,
                        change_type=ChangeType.ADDED,
                    )
                )

        return changes

    def _determine_overall_trend(
        self,
        health_score: MetricChange,
        critical_issues: MetricChange,
        warnings: MetricChange,
    ) -> TrendDirection:
        """Determine the overall trend based on key metrics."""
        # Health score is the primary indicator
        if health_score.trend == TrendDirection.UP:
            return TrendDirection.UP
        elif health_score.trend == TrendDirection.DOWN:
            return TrendDirection.DOWN

        # If health score is stable, check issues
        if critical_issues.trend == TrendDirection.DOWN:
            return TrendDirection.UP
        elif critical_issues.trend == TrendDirection.UP:
            return TrendDirection.DOWN

        return TrendDirection.STABLE

    def _identify_trend_areas(
        self,
        health_score: MetricChange,
        critical_issues: MetricChange,
        warnings: MetricChange,
        suggestions: MetricChange,
        total_documents: MetricChange,
    ) -> tuple[list[str], list[str]]:
        """Identify areas of improvement and degradation."""
        improvements: list[str] = []
        degradations: list[str] = []

        # Health score
        if health_score.trend == TrendDirection.UP:
            change_pct = health_score.change_percent
            improvements.append(
                f"Health score improved by {change_pct:.1f}%"
                if change_pct
                else "Health score improved"
            )
        elif health_score.trend == TrendDirection.DOWN:
            change_pct = health_score.change_percent
            degradations.append(
                f"Health score decreased by {abs(change_pct):.1f}%"
                if change_pct
                else "Health score decreased"
            )

        # Critical issues (lower is better)
        if critical_issues.trend == TrendDirection.DOWN and critical_issues.change < 0:
            improvements.append(
                f"Resolved {abs(int(critical_issues.change))} critical issue(s)"
            )
        elif critical_issues.trend == TrendDirection.UP and critical_issues.change > 0:
            degradations.append(
                f"Added {int(critical_issues.change)} new critical issue(s)"
            )

        # Warnings (lower is better)
        if warnings.trend == TrendDirection.DOWN and warnings.change < 0:
            improvements.append(f"Resolved {abs(int(warnings.change))} warning(s)")
        elif warnings.trend == TrendDirection.UP and warnings.change > 0:
            degradations.append(f"Added {int(warnings.change)} new warning(s)")

        # Document growth
        if total_documents.trend == TrendDirection.UP and total_documents.change > 0:
            change_pct = total_documents.change_percent
            if change_pct and change_pct > 10:
                improvements.append(f"Document count grew by {change_pct:.1f}%")

        return improvements, degradations

    def _generate_recommendations(
        self,
        finding_changes: list[FindingChange],
        index_changes: dict[str, IndexChange],
        overall_trend: TrendDirection,
    ) -> list[str]:
        """Generate recommendations based on the comparison."""
        recommendations: list[str] = []

        # Count new critical issues
        new_critical = [
            fc
            for fc in finding_changes
            if fc.change_type == ChangeType.ADDED
            and fc.finding.severity.value == "critical"
        ]
        if new_critical:
            recommendations.append(
                f"Address {len(new_critical)} new critical issue(s) as soon as possible"
            )

        # Check for degraded indexes
        degraded_indexes = [
            uid
            for uid, change in index_changes.items()
            if change.change_type == ChangeType.DEGRADED
        ]
        if degraded_indexes:
            recommendations.append(
                f"Review degraded indexes: {', '.join(degraded_indexes)}"
            )

        # Check for newly added indexes without optimal settings
        for uid, change in index_changes.items():
            if change.change_type == ChangeType.ADDED and change.new_findings:
                critical_count = sum(
                    1 for f in change.new_findings if f.severity.value == "critical"
                )
                if critical_count > 0:
                    recommendations.append(
                        f"New index '{uid}' has {critical_count} critical issue(s) - configure settings before adding more documents"
                    )

        # Overall trend-based recommendations
        if overall_trend == TrendDirection.UP:
            recommendations.append(
                "Good progress! Continue monitoring and addressing remaining suggestions"
            )
        elif overall_trend == TrendDirection.DOWN:
            recommendations.append(
                "Configuration health has degraded - prioritize fixing critical issues"
            )

        return recommendations
