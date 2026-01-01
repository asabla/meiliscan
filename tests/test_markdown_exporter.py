"""Tests for the Markdown Exporter."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meilisearch_analyzer.exporters.markdown_exporter import MarkdownExporter
from meilisearch_analyzer.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
)
from meilisearch_analyzer.models.report import (
    ActionPlan,
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)


class TestMarkdownExporter:
    """Tests for MarkdownExporter."""

    @pytest.fixture
    def exporter(self) -> MarkdownExporter:
        """Create a markdown exporter instance."""
        return MarkdownExporter()

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
        assert exporter.format_name == "markdown"

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
        assert "# MeiliSearch Analysis Report" in result

    def test_export_contains_source_info(self, exporter, basic_report):
        """Test that export contains source information."""
        result = exporter.export(basic_report)
        assert "**Source:** instance" in result
        assert "**URL:** http://localhost:7700" in result
        assert "**MeiliSearch Version:** 1.7.0" in result

    def test_export_contains_summary(self, exporter, basic_report):
        """Test that export contains summary section."""
        result = exporter.export(basic_report)
        assert "## Summary" in result
        assert "| Total Indexes | 2 |" in result
        assert "| Total Documents | 5,000 |" in result
        assert "| Health Score | 75/100 |" in result
        assert "| Critical Issues | 1 |" in result

    def test_export_contains_health_bar(self, exporter, basic_report):
        """Test that export contains health score bar."""
        result = exporter.export(basic_report)
        assert "**Health:**" in result
        assert "█" in result  # filled blocks
        assert "░" in result  # empty blocks

    def test_export_with_global_findings(self, exporter, basic_report):
        """Test export with global findings."""
        basic_report.global_findings = [
            Finding(
                id="MEILI-P001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.CRITICAL,
                title="High task failure rate",
                description="Task failure rate is 15%.",
                impact="Documents may not be indexed",
            ),
        ]

        result = exporter.export(basic_report)
        assert "## Global Findings" in result
        assert "### 🔴 MEILI-P001: High task failure rate" in result
        assert "Task failure rate is 15%." in result

    def test_export_with_index_findings(self, exporter, basic_report, finding_with_fix):
        """Test export with index findings."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "## Index: `products`" in result
        assert "### Metadata" in result
        assert "| Primary Key | id |" in result
        assert "### Findings" in result
        assert "#### 🔴 MEILI-S001: Wildcard searchable attributes" in result

    def test_export_with_fix_includes_curl(self, exporter, basic_report, finding_with_fix):
        """Test that fix suggestions include curl command."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**Fix:**" in result
        assert "curl -X PATCH" in result
        assert "searchableAttributes" in result

    def test_export_with_references(self, exporter, basic_report, finding_with_fix):
        """Test that references are included."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        assert "**References:**" in result
        assert "[https://docs.meilisearch.com/]" in result

    def test_export_index_without_findings(self, exporter, basic_report):
        """Test export with index without findings."""
        basic_report.indexes["empty_index"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 500},
            findings=[],
        )

        result = exporter.export(basic_report)
        assert "## Index: `empty_index`" in result
        assert "*No findings for this index.*" in result

    def test_export_with_action_plan(self, exporter, basic_report):
        """Test export with action plan."""
        basic_report.action_plan = ActionPlan(
            priority_order=["MEILI-S001", "MEILI-S002", "MEILI-D001"],
            estimated_impact={"search_performance": "+20%", "index_size": "-15%"},
        )

        result = exporter.export(basic_report)
        assert "## Recommended Action Plan" in result
        assert "1. **MEILI-S001**" in result
        assert "2. **MEILI-S002**" in result
        assert "### Estimated Impact" in result
        assert "**Search Performance:** +20%" in result

    def test_export_contains_footer(self, exporter, basic_report):
        """Test that export contains footer."""
        result = exporter.export(basic_report)
        assert "*Generated by MeiliSearch Analyzer v0.1.0*" in result

    def test_export_writes_to_file(self, exporter, basic_report):
        """Test that export writes to file when path provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            result = exporter.export(basic_report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert content == result

    def test_severity_icons(self, exporter):
        """Test severity icon mapping."""
        assert exporter.SEVERITY_ICONS[FindingSeverity.CRITICAL] == "🔴"
        assert exporter.SEVERITY_ICONS[FindingSeverity.WARNING] == "🟡"
        assert exporter.SEVERITY_ICONS[FindingSeverity.SUGGESTION] == "🔵"
        assert exporter.SEVERITY_ICONS[FindingSeverity.INFO] == "⚪"

    def test_export_sorted_by_severity(self, exporter, basic_report):
        """Test that findings are sorted by severity."""
        basic_report.indexes["test"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 100},
            findings=[
                Finding(
                    id="INFO-1",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.INFO,
                    title="Info finding",
                    description="Low priority",
                    impact="Minimal",
                    index_uid="test",
                ),
                Finding(
                    id="CRITICAL-1",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Critical finding",
                    description="High priority",
                    impact="High",
                    index_uid="test",
                ),
                Finding(
                    id="WARNING-1",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title="Warning finding",
                    description="Medium priority",
                    impact="Medium",
                    index_uid="test",
                ),
            ],
        )

        result = exporter.export(basic_report)

        # Critical should appear before warning, warning before info
        critical_pos = result.find("CRITICAL-1")
        warning_pos = result.find("WARNING-1")
        info_pos = result.find("INFO-1")

        assert critical_pos < warning_pos < info_pos

    def test_export_current_value_json(self, exporter, basic_report):
        """Test that current values are JSON formatted."""
        basic_report.indexes["test"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 100},
            findings=[
                Finding(
                    id="TEST-1",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title="Test finding",
                    description="Test",
                    impact="Test",
                    index_uid="test",
                    current_value={"key": "value"},
                ),
            ],
        )

        result = exporter.export(basic_report)
        assert "```json" in result
        assert '"key": "value"' in result

    def test_export_empty_report(self, exporter):
        """Test export of empty report."""
        empty_report = AnalysisReport(
            version="0.1.0",
            source=SourceInfo(type="instance"),
            generated_at=datetime.now(timezone.utc),
            summary=AnalysisSummary(),
        )

        result = exporter.export(empty_report)
        assert "# MeiliSearch Analysis Report" in result
        assert "## Summary" in result

    def test_export_dump_source(self, exporter):
        """Test export with dump source type."""
        report = AnalysisReport(
            version="0.1.0",
            source=SourceInfo(
                type="dump",
                dump_path="/path/to/dump.dump",
            ),
            generated_at=datetime.now(timezone.utc),
            summary=AnalysisSummary(),
        )

        result = exporter.export(report)
        assert "**Source:** dump" in result
