"""Markdown exporter for analysis reports."""

import json
from pathlib import Path

from meilisearch_analyzer.exporters.base import BaseExporter
from meilisearch_analyzer.models.finding import FindingSeverity
from meilisearch_analyzer.models.report import AnalysisReport


class MarkdownExporter(BaseExporter):
    """Export reports to Markdown format."""

    SEVERITY_ICONS = {
        FindingSeverity.CRITICAL: "🔴",
        FindingSeverity.WARNING: "🟡",
        FindingSeverity.SUGGESTION: "🔵",
        FindingSeverity.INFO: "⚪",
    }

    @property
    def format_name(self) -> str:
        return "markdown"

    @property
    def file_extension(self) -> str:
        return ".md"

    def export(self, report: AnalysisReport, output_path: Path | None = None) -> str:
        """Export the report to Markdown format.

        Args:
            report: The analysis report to export
            output_path: Optional path to write the Markdown to

        Returns:
            The Markdown string
        """
        lines: list[str] = []

        # Header
        lines.append("# MeiliSearch Analysis Report")
        lines.append("")
        lines.append(f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Source:** {report.source.type}")
        if report.source.url:
            lines.append(f"**URL:** {report.source.url}")
        if report.source.meilisearch_version:
            lines.append(f"**MeiliSearch Version:** {report.source.meilisearch_version}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Indexes | {report.summary.total_indexes} |")
        lines.append(f"| Total Documents | {report.summary.total_documents:,} |")
        lines.append(f"| Health Score | {report.summary.health_score}/100 |")
        lines.append(f"| Critical Issues | {report.summary.critical_issues} |")
        lines.append(f"| Warnings | {report.summary.warnings} |")
        lines.append(f"| Suggestions | {report.summary.suggestions} |")
        lines.append("")

        # Health Score Bar
        filled = int(report.summary.health_score / 5)
        empty = 20 - filled
        score_bar = "█" * filled + "░" * empty
        lines.append(f"**Health:** `{score_bar}` {report.summary.health_score}/100")
        lines.append("")

        # Global Findings
        if report.global_findings:
            lines.append("## Global Findings")
            lines.append("")
            for finding in sorted(
                report.global_findings,
                key=lambda f: (
                    0 if f.severity == FindingSeverity.CRITICAL else
                    1 if f.severity == FindingSeverity.WARNING else
                    2 if f.severity == FindingSeverity.SUGGESTION else 3
                ),
            ):
                icon = self.SEVERITY_ICONS.get(finding.severity, "⚪")
                lines.append(f"### {icon} {finding.id}: {finding.title}")
                lines.append("")
                lines.append(f"**Severity:** {finding.severity.value}")
                lines.append(f"**Category:** {finding.category.value}")
                lines.append("")
                lines.append(finding.description)
                lines.append("")
                lines.append(f"**Impact:** {finding.impact}")
                lines.append("")
                if finding.current_value is not None:
                    lines.append(f"**Current Value:** `{finding.current_value}`")
                if finding.recommended_value is not None:
                    lines.append(f"**Recommended:** `{finding.recommended_value}`")
                lines.append("")
                lines.append("---")
                lines.append("")

        # Index Findings
        for index_uid, index_analysis in report.indexes.items():
            lines.append(f"## Index: `{index_uid}`")
            lines.append("")

            # Index metadata
            metadata = index_analysis.metadata
            lines.append("### Metadata")
            lines.append("")
            lines.append(f"| Property | Value |")
            lines.append("|----------|-------|")
            lines.append(f"| Primary Key | {metadata.get('primary_key', 'N/A')} |")
            lines.append(f"| Document Count | {metadata.get('document_count', 0):,} |")
            lines.append("")

            # Index findings
            if index_analysis.findings:
                lines.append("### Findings")
                lines.append("")
                for finding in sorted(
                    index_analysis.findings,
                    key=lambda f: (
                        0 if f.severity == FindingSeverity.CRITICAL else
                        1 if f.severity == FindingSeverity.WARNING else
                        2 if f.severity == FindingSeverity.SUGGESTION else 3
                    ),
                ):
                    icon = self.SEVERITY_ICONS.get(finding.severity, "⚪")
                    lines.append(f"#### {icon} {finding.id}: {finding.title}")
                    lines.append("")
                    lines.append(f"**Severity:** {finding.severity.value} | **Category:** {finding.category.value}")
                    lines.append("")
                    lines.append(finding.description)
                    lines.append("")
                    lines.append(f"**Impact:** {finding.impact}")
                    lines.append("")

                    if finding.current_value is not None:
                        lines.append(f"**Current Value:**")
                        lines.append("```json")
                        lines.append(json.dumps(finding.current_value, indent=2))
                        lines.append("```")
                        lines.append("")

                    if finding.recommended_value is not None:
                        lines.append(f"**Recommended:**")
                        lines.append("```json")
                        lines.append(json.dumps(finding.recommended_value, indent=2))
                        lines.append("```")
                        lines.append("")

                    if finding.fix:
                        lines.append("**Fix:**")
                        lines.append("```bash")
                        lines.append(f"# {finding.fix.endpoint}")
                        lines.append(f"curl -X PATCH '<your-meilisearch-url>{finding.fix.endpoint.split(' ')[1]}' \\")
                        lines.append("  -H 'Content-Type: application/json' \\")
                        lines.append("  -H 'Authorization: Bearer <your-api-key>' \\")
                        payload_json = json.dumps(finding.fix.payload, indent=2)
                        lines.append(f"  --data-binary '{payload_json}'")
                        lines.append("```")
                        lines.append("")

                    if finding.references:
                        lines.append("**References:**")
                        for ref in finding.references:
                            lines.append(f"- [{ref}]({ref})")
                        lines.append("")

                    lines.append("---")
                    lines.append("")
            else:
                lines.append("*No findings for this index.*")
                lines.append("")

        # Action Plan
        if report.action_plan.priority_order:
            lines.append("## Recommended Action Plan")
            lines.append("")
            lines.append("Fix issues in this order:")
            lines.append("")
            for i, finding_id in enumerate(report.action_plan.priority_order[:10], 1):
                lines.append(f"{i}. **{finding_id}**")
            lines.append("")

            if report.action_plan.estimated_impact:
                lines.append("### Estimated Impact")
                lines.append("")
                for metric, value in report.action_plan.estimated_impact.items():
                    lines.append(f"- **{metric.replace('_', ' ').title()}:** {value}")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Generated by MeiliSearch Analyzer v{report.version}*")

        content = "\n".join(lines)

        if output_path:
            output_path.write_text(content)

        return content
