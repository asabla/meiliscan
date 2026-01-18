"""SARIF exporter for analysis reports.

SARIF (Static Analysis Results Interchange Format) is an OASIS standard
for the output format of static analysis tools. This exporter generates
SARIF 2.1.0 compliant output for integration with GitHub Code Scanning,
VS Code, and other SARIF-compatible tools.
"""

from pathlib import Path
from typing import Any

import orjson

from meiliscan.exporters.base import BaseExporter
from meiliscan.models.finding import Finding, FindingSeverity
from meiliscan.models.report import AnalysisReport

# SARIF version
SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"

# Tool info
TOOL_NAME = "meiliscan"
TOOL_INFO_URI = "https://github.com/meilisearch/meiliscan"
TOOL_VERSION = "0.1.0"


class SarifExporter(BaseExporter):
    """Export reports to SARIF format for CI/CD integration."""

    def __init__(self, include_fixes: bool = True):
        """Initialize the SARIF exporter.

        Args:
            include_fixes: Whether to include fix suggestions in the output
        """
        self.include_fixes = include_fixes

    @property
    def format_name(self) -> str:
        return "sarif"

    @property
    def file_extension(self) -> str:
        return ".sarif"

    def export(self, report: AnalysisReport, output_path: Path | None = None) -> str:
        """Export the report to SARIF format.

        Args:
            report: The analysis report to export
            output_path: Optional path to write the SARIF file to

        Returns:
            The SARIF JSON string
        """
        sarif_output = self._build_sarif(report)

        json_bytes = orjson.dumps(sarif_output, option=orjson.OPT_INDENT_2)
        json_str = json_bytes.decode("utf-8")

        if output_path:
            output_path.write_text(json_str)

        return json_str

    def _build_sarif(self, report: AnalysisReport) -> dict[str, Any]:
        """Build the complete SARIF document structure."""
        all_findings = self._collect_all_findings(report)
        rules = self._build_rules(all_findings)
        results = self._build_results(all_findings)

        return {
            "$schema": SARIF_SCHEMA,
            "version": SARIF_VERSION,
            "runs": [
                {
                    "tool": self._build_tool(rules),
                    "results": results,
                    "invocations": [self._build_invocation(report)],
                }
            ],
        }

    def _collect_all_findings(self, report: AnalysisReport) -> list[Finding]:
        """Collect all findings from the report."""
        all_findings = list(report.global_findings)
        for index_data in report.indexes.values():
            all_findings.extend(index_data.findings)
        return all_findings

    def _build_tool(self, rules: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the tool descriptor."""
        return {
            "driver": {
                "name": TOOL_NAME,
                "version": TOOL_VERSION,
                "informationUri": TOOL_INFO_URI,
                "rules": rules,
            }
        }

    def _build_rules(self, findings: list[Finding]) -> list[dict[str, Any]]:
        """Build SARIF rule definitions from findings.

        Each unique finding ID becomes a rule.
        """
        seen_ids: set[str] = set()
        rules = []

        for finding in findings:
            if finding.id in seen_ids:
                continue
            seen_ids.add(finding.id)

            rule = {
                "id": finding.id,
                "name": self._to_pascal_case(finding.title),
                "shortDescription": {"text": finding.title},
                "fullDescription": {"text": finding.description},
                "helpUri": finding.references[0] if finding.references else None,
                "defaultConfiguration": {
                    "level": self._severity_to_level(finding.severity)
                },
                "properties": {
                    "category": finding.category.value,
                    "tags": [finding.category.value, finding.severity.value],
                },
            }

            # Remove None values
            if rule["helpUri"] is None:
                del rule["helpUri"]

            rules.append(rule)

        return rules

    def _build_results(self, findings: list[Finding]) -> list[dict[str, Any]]:
        """Build SARIF results from findings."""
        results = []

        for finding in findings:
            result = {
                "ruleId": finding.id,
                "level": self._severity_to_level(finding.severity),
                "message": {"text": self._build_message(finding)},
                "locations": [self._build_location(finding)],
                "properties": {
                    "impact": finding.impact,
                },
            }

            # Add current/recommended values if present
            if finding.current_value is not None:
                result["properties"]["currentValue"] = self._safe_value(
                    finding.current_value
                )
            if finding.recommended_value is not None:
                result["properties"]["recommendedValue"] = self._safe_value(
                    finding.recommended_value
                )

            # Add fix information if enabled and available
            if self.include_fixes and finding.fix:
                result["fixes"] = [self._build_fix(finding)]

            results.append(result)

        return results

    def _build_location(self, finding: Finding) -> dict[str, Any]:
        """Build SARIF location for a finding.

        Since MeiliSearch is a database, we use logical locations
        (index paths) rather than physical file locations.
        """
        if finding.index_uid:
            logical_location = f"indexes/{finding.index_uid}/settings"
        else:
            logical_location = "instance/global"

        return {
            "logicalLocations": [
                {
                    "name": finding.index_uid or "global",
                    "fullyQualifiedName": logical_location,
                    "kind": "database",
                }
            ]
        }

    def _build_invocation(self, report: AnalysisReport) -> dict[str, Any]:
        """Build SARIF invocation info."""
        invocation: dict[str, Any] = {
            "executionSuccessful": True,
            "endTimeUtc": report.generated_at.isoformat() + "Z"
            if report.generated_at
            else None,
        }

        # Add source information
        if report.source:
            invocation["arguments"] = []
            if report.source.type:
                invocation["arguments"].append(f"--source-type={report.source.type}")
            if report.source.url:
                invocation["arguments"].append(f"--url={report.source.url}")

        # Remove None values
        invocation = {k: v for k, v in invocation.items() if v is not None}

        return invocation

    def _build_fix(self, finding: Finding) -> dict[str, Any]:
        """Build SARIF fix suggestion."""
        if not finding.fix:
            return {}

        fix_description = f"Apply via: {finding.fix.endpoint}"
        if finding.fix.payload:
            payload_str = orjson.dumps(finding.fix.payload).decode("utf-8")
            fix_description += f"\nPayload: {payload_str}"

        return {
            "description": {"text": fix_description},
            "artifactChanges": [
                {
                    "artifactLocation": {
                        "uri": finding.fix.endpoint,
                    },
                    "replacements": [
                        {
                            "deletedRegion": {"startLine": 1, "startColumn": 1},
                            "insertedContent": {
                                "text": orjson.dumps(finding.fix.payload).decode(
                                    "utf-8"
                                )
                            },
                        }
                    ],
                }
            ],
        }

    def _build_message(self, finding: Finding) -> str:
        """Build a descriptive message for a finding."""
        parts = [finding.description]

        if finding.index_uid:
            parts.append(f"Index: {finding.index_uid}")

        if finding.impact:
            parts.append(f"Impact: {finding.impact}")

        return " | ".join(parts)

    def _severity_to_level(self, severity: FindingSeverity) -> str:
        """Convert finding severity to SARIF level.

        SARIF levels: error, warning, note, none
        """
        mapping = {
            FindingSeverity.CRITICAL: "error",
            FindingSeverity.WARNING: "warning",
            FindingSeverity.SUGGESTION: "note",
            FindingSeverity.INFO: "none",
        }
        return mapping.get(severity, "note")

    def _to_pascal_case(self, text: str) -> str:
        """Convert text to PascalCase for rule names."""
        words = text.replace("-", " ").replace("_", " ").split()
        return "".join(word.capitalize() for word in words)

    def _safe_value(self, value: Any) -> Any:
        """Convert value to JSON-safe format."""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (list, tuple)):
            return [self._safe_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._safe_value(v) for k, v in value.items()}
        return str(value)
