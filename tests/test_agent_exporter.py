"""Tests for the Agent Exporter."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meilisearch_analyzer.exporters.agent_exporter import AgentExporter
from meilisearch_analyzer.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
)
from meilisearch_analyzer.models.report import (
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)


class TestAgentExporter:
    """Tests for AgentExporter."""

    @pytest.fixture
    def exporter(self) -> AgentExporter:
        """Create an agent exporter instance."""
        return AgentExporter()

    @pytest.fixture
    def basic_report(self) -> AnalysisReport:
        """Create a basic report for testing."""
        return AnalysisReport(
            version="0.1.0",
            source=SourceInfo(
                type="instance",
                url="http://localhost:7700",
                meilisearch_version="1.7.0",
            ),
            generated_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            summary=AnalysisSummary(
                total_indexes=2,
                total_documents=5000,
                database_size_bytes=1024 * 1024 * 500,  # 500MB
                health_score=75,
                critical_issues=1,
                warnings=3,
                suggestions=2,
            ),
        )

    @pytest.fixture
    def finding_with_fix(self) -> Finding:
        """Create a finding with fix suggestion."""
        return Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Wildcard searchable attributes",
            description="All fields are searchable by default.",
            impact="Poor search performance",
            index_uid="products",
            current_value=["*"],
            recommended_value=["title", "description"],
            fix=FindingFix(
                type="settings_update",
                endpoint="PATCH /indexes/products/settings",
                payload={"searchableAttributes": ["title", "description"]},
            ),
            references=["https://docs.meilisearch.com/"],
        )

    def test_exporter_format_name(self, exporter):
        """Test exporter format name property."""
        assert exporter.format_name == "agent"

    def test_exporter_file_extension(self, exporter):
        """Test exporter file extension property."""
        assert exporter.file_extension == ".md"

    def test_export_returns_string(self, exporter, basic_report):
        """Test that export returns a string."""
        result = exporter.export(basic_report)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_export_contains_header(self, exporter, basic_report):
        """Test that export contains report header."""
        result = exporter.export(basic_report)
        assert "# MeiliSearch Analysis Context" in result

    def test_export_contains_summary(self, exporter, basic_report):
        """Test that export contains summary section."""
        result = exporter.export(basic_report)
        assert "## Current State Summary" in result
        assert "2 indexes" in result
        assert "5,000 documents" in result
        assert "500.0MB database" in result

    def test_export_contains_health_score(self, exporter, basic_report):
        """Test that export contains health score."""
        result = exporter.export(basic_report)
        assert "Health Score:" in result
        assert "75/100" in result
        assert "good" in result

    def test_export_contains_issue_counts(self, exporter, basic_report):
        """Test that export contains issue counts."""
        result = exporter.export(basic_report)
        assert "1 critical" in result
        assert "3 warnings" in result
        assert "2 suggestions" in result

    def test_export_contains_url(self, exporter, basic_report):
        """Test that export contains source URL."""
        result = exporter.export(basic_report)
        assert "`http://localhost:7700`" in result

    def test_export_contains_version(self, exporter, basic_report):
        """Test that export contains MeiliSearch version."""
        result = exporter.export(basic_report)
        assert "1.7.0" in result

    def test_export_with_critical_findings(self, exporter, basic_report, finding_with_fix):
        """Test export with critical findings."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "## Critical Issues (Fix First)" in result
        assert "### MEILI-S001: Wildcard searchable attributes" in result

    def test_export_with_warning_findings(self, exporter, basic_report):
        """Test export with warning findings."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="Test warning",
                description="Test warning description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        assert "## Warnings (Should Address)" in result
        assert "### TEST-001: Test warning" in result

    def test_export_with_suggestion_findings(self, exporter, basic_report):
        """Test export with suggestion findings."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.SUGGESTION,
                title="Test suggestion",
                description="Test suggestion description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        assert "## Suggestions (Consider When Convenient)" in result

    def test_export_with_info_findings(self, exporter, basic_report):
        """Test export with info findings."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.INFO,
                title="Test info",
                description="Test info description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        assert "## Informational Notes" in result

    def test_export_finding_includes_index(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes index information."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Index:** `products`" in result

    def test_export_finding_includes_problem(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes problem description."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Problem:** All fields are searchable by default." in result

    def test_export_finding_includes_impact(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes impact."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Impact:** Poor search performance" in result

    def test_export_finding_includes_current_value(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes current value."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Current Configuration:**" in result
        assert '"*"' in result  # Value is formatted with indentation

    def test_export_finding_includes_recommended(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes recommended value."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Recommended:**" in result
        assert '"title"' in result
        assert '"description"' in result

    def test_export_finding_includes_fix_command(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes fix command."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Fix Command:**" in result
        assert "curl -X PATCH" in result
        assert "/indexes/products/settings" in result

    def test_export_finding_includes_references(self, exporter, basic_report, finding_with_fix):
        """Test that finding includes references."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**References:**" in result
        assert "https://docs.meilisearch.com/" in result

    def test_export_includes_quick_fix_script(self, exporter, basic_report, finding_with_fix):
        """Test that export includes quick fix script."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "## Quick Fix Script" in result
        assert "#!/bin/bash" in result
        assert 'MEILISEARCH_URL="http://localhost:7700"' in result
        assert "API_KEY=" in result

    def test_export_includes_index_overview(self, exporter, basic_report):
        """Test that export includes index overview table."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[],
        )
        basic_report.indexes["orders"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 500},
            findings=[],
        )

        result = exporter.export(basic_report)
        assert "## Index Overview" in result
        assert "| Index | Documents | Findings | Top Issue |" in result
        assert "`products`" in result
        assert "`orders`" in result

    def test_export_sorted_by_severity(self, exporter, basic_report):
        """Test that findings are sorted by severity."""
        basic_report.global_findings = [
            Finding(
                id="INFO-1",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.INFO,
                title="Info finding",
                description="Test",
                impact="Test",
            ),
            Finding(
                id="CRITICAL-1",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.CRITICAL,
                title="Critical finding",
                description="Test",
                impact="Test",
            ),
            Finding(
                id="WARNING-1",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.WARNING,
                title="Warning finding",
                description="Test",
                impact="Test",
            ),
        ]

        result = exporter.export(basic_report)

        # Critical should appear before warning, warning before info
        critical_pos = result.find("CRITICAL-1")
        warning_pos = result.find("WARNING-1")
        info_pos = result.find("INFO-1")

        assert critical_pos < warning_pos < info_pos

    def test_export_exclude_suggestions(self):
        """Test export with include_all_findings=False."""
        exporter = AgentExporter(include_all_findings=False)
        report = AnalysisReport(
            version="0.1.0",
            source=SourceInfo(type="instance"),
            generated_at=datetime.now(timezone.utc),
            summary=AnalysisSummary(),
            global_findings=[
                Finding(
                    id="SUGGESTION-1",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="Test suggestion",
                    description="Test",
                    impact="Test",
                ),
                Finding(
                    id="WARNING-1",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title="Test warning",
                    description="Test",
                    impact="Test",
                ),
            ],
        )

        result = exporter.export(report)

        assert "WARNING-1" in result
        # Suggestion section should not appear when include_all_findings=False
        assert "## Suggestions" not in result

    def test_export_max_findings(self):
        """Test export with max_findings limit."""
        exporter = AgentExporter(max_findings=2)
        report = AnalysisReport(
            version="0.1.0",
            source=SourceInfo(type="instance"),
            generated_at=datetime.now(timezone.utc),
            summary=AnalysisSummary(),
            global_findings=[
                Finding(
                    id=f"TEST-{i}",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title=f"Test {i}",
                    description="Test",
                    impact="Test",
                )
                for i in range(5)
            ],
        )

        result = exporter.export(report)

        # Only first 2 should appear
        assert "TEST-0" in result
        assert "TEST-1" in result
        assert "TEST-2" not in result
        assert "TEST-3" not in result
        assert "TEST-4" not in result

    def test_export_writes_to_file(self, exporter, basic_report):
        """Test that export writes to file when path provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "agent-context.md"
            result = exporter.export(basic_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert content == result

    def test_export_empty_report(self, exporter):
        """Test export of empty report."""
        empty_report = AnalysisReport(
            version="0.1.0",
            source=SourceInfo(type="instance"),
            generated_at=datetime.now(timezone.utc),
            summary=AnalysisSummary(),
        )

        result = exporter.export(empty_report)
        assert "# MeiliSearch Analysis Context" in result
        assert "## Current State Summary" in result

    def test_health_status_excellent(self, exporter):
        """Test health status for excellent score."""
        assert exporter._get_health_status(95) == "excellent"
        assert exporter._get_health_status(90) == "excellent"

    def test_health_status_good(self, exporter):
        """Test health status for good score."""
        assert exporter._get_health_status(85) == "good"
        assert exporter._get_health_status(75) == "good"

    def test_health_status_needs_attention(self, exporter):
        """Test health status for needs attention score."""
        assert exporter._get_health_status(60) == "needs attention"
        assert exporter._get_health_status(50) == "needs attention"

    def test_health_status_poor(self, exporter):
        """Test health status for poor score."""
        assert exporter._get_health_status(40) == "poor"
        assert exporter._get_health_status(25) == "poor"

    def test_health_status_critical(self, exporter):
        """Test health status for critical score."""
        assert exporter._get_health_status(20) == "critical"
        assert exporter._get_health_status(0) == "critical"

    def test_export_large_database_gb(self):
        """Test that large database sizes show in GB."""
        exporter = AgentExporter()
        report = AnalysisReport(
            version="0.1.0",
            source=SourceInfo(type="instance"),
            generated_at=datetime.now(timezone.utc),
            summary=AnalysisSummary(
                database_size_bytes=1024 * 1024 * 1024 * 4,  # 4GB
            ),
        )

        result = exporter.export(report)
        assert "4.0GB database" in result

    def test_export_global_and_index_findings(self, exporter, basic_report, finding_with_fix):
        """Test that both global and index findings are included."""
        basic_report.global_findings = [
            Finding(
                id="GLOBAL-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="Global warning",
                description="Test",
                impact="Test",
            ),
        ]
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)

        assert "GLOBAL-001" in result
        assert "MEILI-S001" in result
