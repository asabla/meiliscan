"""Agent-friendly exporter for analysis reports.

This exporter generates a structured markdown format optimized for
AI coding agents (Claude, GPT, etc.). It includes clear sections,
actionable fix commands, and prioritized issues.
"""

from pathlib import Path
from typing import Any

import orjson

from meiliscan.exporters.base import BaseExporter
from meiliscan.models.finding import Finding, FindingSeverity
from meiliscan.models.report import AnalysisReport

# Severity priority for sorting (lower = higher priority)
SEVERITY_PRIORITY = {
    FindingSeverity.CRITICAL: 0,
    FindingSeverity.WARNING: 1,
    FindingSeverity.SUGGESTION: 2,
    FindingSeverity.INFO: 3,
}


class AgentExporter(BaseExporter):
    """Export reports in an AI agent-friendly markdown format.

    This format is structured to be easily parsed by AI coding agents,
    with clear sections, code blocks for fix commands, and prioritized issues.
    """

    def __init__(
        self, include_all_findings: bool = True, max_findings: int | None = None
    ):
        """Initialize the agent exporter.

        Args:
            include_all_findings: Whether to include all findings or just critical/warning
            max_findings: Maximum number of findings to include (None for all)
        """
        self.include_all_findings = include_all_findings
        self.max_findings = max_findings

    @property
    def format_name(self) -> str:
        return "agent"

    @property
    def file_extension(self) -> str:
        return ".md"

    def export(self, report: AnalysisReport, output_path: Path | None = None) -> str:
        """Export the report in agent-friendly markdown format.

        Args:
            report: The analysis report to export
            output_path: Optional path to write the output to

        Returns:
            The formatted markdown string
        """
        lines = []

        # Header
        lines.extend(self._build_header(report))

        # Summary
        lines.extend(self._build_summary(report))

        # Collect and sort findings
        all_findings = self._collect_and_sort_findings(report)

        # Filter if needed
        if not self.include_all_findings:
            all_findings = [
                f
                for f in all_findings
                if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.WARNING)
            ]

        if self.max_findings:
            all_findings = all_findings[: self.max_findings]

        # Critical issues section
        critical = [f for f in all_findings if f.severity == FindingSeverity.CRITICAL]
        if critical:
            lines.extend(
                self._build_issues_section(
                    "Critical Issues (Fix First)",
                    critical,
                    report.source.url if report.source else None,
                )
            )

        # Warning section
        warnings = [f for f in all_findings if f.severity == FindingSeverity.WARNING]
        if warnings:
            lines.extend(
                self._build_issues_section(
                    "Warnings (Should Address)",
                    warnings,
                    report.source.url if report.source else None,
                )
            )

        # Suggestions section
        suggestions = [
            f for f in all_findings if f.severity == FindingSeverity.SUGGESTION
        ]
        if suggestions and self.include_all_findings:
            lines.extend(
                self._build_issues_section(
                    "Suggestions (Consider When Convenient)",
                    suggestions,
                    report.source.url if report.source else None,
                )
            )

        # Info section
        info = [f for f in all_findings if f.severity == FindingSeverity.INFO]
        if info and self.include_all_findings:
            lines.extend(
                self._build_issues_section(
                    "Informational Notes",
                    info,
                    report.source.url if report.source else None,
                )
            )

        # Quick fix script section
        fixable_findings = [f for f in all_findings if f.fix]
        if fixable_findings:
            lines.extend(
                self._build_quick_fix_section(
                    fixable_findings,
                    report.source.url if report.source else None,
                )
            )

        # Index overview
        if report.indexes:
            lines.extend(self._build_index_overview(report))

        content = "\n".join(lines)

        if output_path:
            output_path.write_text(content)

        return content

    def _build_header(self, report: AnalysisReport) -> list[str]:
        """Build the header section."""
        lines = [
            "# MeiliSearch Analysis Context",
            "",
            "This document contains analysis results for your MeiliSearch instance.",
            "Use this context to understand issues and apply fixes.",
            "",
        ]
        return lines

    def _build_summary(self, report: AnalysisReport) -> list[str]:
        """Build the current state summary."""
        lines = [
            "## Current State Summary",
            "",
        ]

        summary = report.summary
        source = report.source

        # Key metrics
        metrics = []

        if summary.total_indexes:
            metrics.append(f"{summary.total_indexes} indexes")
        if summary.total_documents:
            metrics.append(f"{summary.total_documents:,} documents")
        if summary.database_size_bytes:
            size_mb = summary.database_size_bytes / (1024 * 1024)
            if size_mb >= 1024:
                metrics.append(f"{size_mb / 1024:.1f}GB database")
            else:
                metrics.append(f"{size_mb:.1f}MB database")

        if metrics:
            lines.append(f"- **Instance:** {', '.join(metrics)}")

        # Health score
        if summary.health_score is not None:
            health_status = self._get_health_status(summary.health_score)
            lines.append(
                f"- **Health Score:** {summary.health_score}/100 ({health_status})"
            )

        # Issue counts
        issue_parts = []
        if summary.critical_issues:
            issue_parts.append(f"{summary.critical_issues} critical")
        if summary.warnings:
            issue_parts.append(f"{summary.warnings} warnings")
        if summary.suggestions:
            issue_parts.append(f"{summary.suggestions} suggestions")

        if issue_parts:
            lines.append(f"- **Issues Found:** {', '.join(issue_parts)}")

        # Source info
        if source:
            if source.url:
                lines.append(f"- **URL:** `{source.url}`")
            if source.meilisearch_version:
                lines.append(f"- **Version:** {source.meilisearch_version}")

        lines.append("")
        return lines

    def _build_issues_section(
        self,
        title: str,
        findings: list[Finding],
        base_url: str | None,
    ) -> list[str]:
        """Build an issues section."""
        lines = [
            f"## {title}",
            "",
        ]

        for finding in findings:
            lines.extend(self._format_finding(finding, base_url))

        return lines

    def _format_finding(self, finding: Finding, base_url: str | None) -> list[str]:
        """Format a single finding."""
        lines = [
            f"### {finding.id}: {finding.title}",
            "",
        ]

        if finding.index_uid:
            lines.append(f"**Index:** `{finding.index_uid}`")
            lines.append("")

        lines.append(f"**Problem:** {finding.description}")
        lines.append("")

        if finding.impact:
            lines.append(f"**Impact:** {finding.impact}")
            lines.append("")

        if finding.current_value is not None:
            lines.append("**Current Configuration:**")
            lines.append("```json")
            lines.append(self._format_value(finding.current_value))
            lines.append("```")
            lines.append("")

        if finding.recommended_value is not None:
            lines.append("**Recommended:**")
            lines.append("```json")
            lines.append(self._format_value(finding.recommended_value))
            lines.append("```")
            lines.append("")

        if finding.fix:
            lines.append("**Fix Command:**")
            lines.append("```bash")
            lines.append(self._generate_curl_command(finding, base_url))
            lines.append("```")
            lines.append("")

        if finding.references:
            lines.append("**References:**")
            for ref in finding.references:
                lines.append(f"- {ref}")
            lines.append("")

        return lines

    def _build_quick_fix_section(
        self,
        findings: list[Finding],
        base_url: str | None,
    ) -> list[str]:
        """Build a combined quick fix script section."""
        lines = [
            "## Quick Fix Script",
            "",
            "Run these commands to apply recommended fixes:",
            "",
            "```bash",
            "#!/bin/bash",
            "# MeiliSearch Configuration Fix Script",
            "# Generated by Meiliscan",
            "",
            f'MEILISEARCH_URL="{base_url or "http://localhost:7700"}"',
            'API_KEY="YOUR_API_KEY"  # Replace with your API key',
            "",
        ]

        for finding in findings:
            if finding.fix:
                lines.append(f"# Fix: {finding.id} - {finding.title}")
                if finding.index_uid:
                    lines.append(f"# Index: {finding.index_uid}")

                method = "PATCH"
                endpoint = finding.fix.endpoint
                if endpoint.startswith("PATCH "):
                    method = "PATCH"
                    endpoint = endpoint[6:]
                elif endpoint.startswith("PUT "):
                    method = "PUT"
                    endpoint = endpoint[4:]
                elif endpoint.startswith("POST "):
                    method = "POST"
                    endpoint = endpoint[5:]
                elif endpoint.startswith("DELETE "):
                    method = "DELETE"
                    endpoint = endpoint[7:]

                payload_json = orjson.dumps(
                    finding.fix.payload, option=orjson.OPT_INDENT_2
                ).decode("utf-8")

                # Escape for shell
                payload_escaped = payload_json.replace("'", "'\"'\"'")

                lines.append(f'curl -X {method} "$MEILISEARCH_URL{endpoint}" \\')
                lines.append("  -H 'Content-Type: application/json' \\")
                lines.append('  -H "Authorization: Bearer $API_KEY" \\')
                lines.append(f"  --data-binary '{payload_escaped}'")
                lines.append("")

        lines.append("echo 'Fixes applied!'")
        lines.append("```")
        lines.append("")

        return lines

    def _build_index_overview(self, report: AnalysisReport) -> list[str]:
        """Build index overview section."""
        lines = [
            "## Index Overview",
            "",
            "| Index | Documents | Findings | Top Issue |",
            "|-------|-----------|----------|-----------|",
        ]

        for index_uid, index_data in report.indexes.items():
            doc_count = index_data.metadata.get("document_count", "N/A")
            if isinstance(doc_count, int):
                doc_count = f"{doc_count:,}"

            finding_count = len(index_data.findings)

            top_issue = "None"
            if index_data.findings:
                # Sort by severity and take first
                sorted_findings = sorted(
                    index_data.findings,
                    key=lambda f: SEVERITY_PRIORITY.get(f.severity, 99),
                )
                top = sorted_findings[0]
                top_issue = f"{top.id}: {top.title[:30]}..."

            lines.append(
                f"| `{index_uid}` | {doc_count} | {finding_count} | {top_issue} |"
            )

        lines.append("")
        return lines

    def _collect_and_sort_findings(self, report: AnalysisReport) -> list[Finding]:
        """Collect all findings and sort by severity."""
        all_findings = list(report.global_findings)

        for index_data in report.indexes.values():
            all_findings.extend(index_data.findings)

        return sorted(all_findings, key=lambda f: SEVERITY_PRIORITY.get(f.severity, 99))

    def _get_health_status(self, score: int) -> str:
        """Get health status description from score."""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 50:
            return "needs attention"
        elif score >= 25:
            return "poor"
        else:
            return "critical"

    def _format_value(self, value: Any) -> str:
        """Format a value as pretty JSON."""
        return orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")

    def _generate_curl_command(self, finding: Finding, base_url: str | None) -> str:
        """Generate a curl command for a fix."""
        if not finding.fix:
            return "# No fix available"

        url = base_url or "http://localhost:7700"

        method = "PATCH"
        endpoint = finding.fix.endpoint
        if endpoint.startswith("PATCH "):
            method = "PATCH"
            endpoint = endpoint[6:]
        elif endpoint.startswith("PUT "):
            method = "PUT"
            endpoint = endpoint[4:]
        elif endpoint.startswith("POST "):
            method = "POST"
            endpoint = endpoint[5:]

        payload_json = orjson.dumps(finding.fix.payload).decode("utf-8")

        return (
            f"curl -X {method} '{url}{endpoint}' \\\n"
            f"  -H 'Content-Type: application/json' \\\n"
            f"  -H 'Authorization: Bearer YOUR_API_KEY' \\\n"
            f"  --data-binary '{payload_json}'"
        )
