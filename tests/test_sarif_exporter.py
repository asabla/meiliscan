"""Tests for the SARIF Exporter."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meiliscan.exporters.sarif_exporter import (
    SARIF_SCHEMA,
    SARIF_VERSION,
    TOOL_NAME,
    TOOL_VERSION,
    SarifExporter,
)
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
)
from meiliscan.models.report import (
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)


class TestSarifExporter:
    """Tests for SarifExporter."""

    @pytest.fixture
    def exporter(self) -> SarifExporter:
        """Create a SARIF exporter instance."""
        return SarifExporter()

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
        assert exporter.format_name == "sarif"

    def test_exporter_file_extension(self, exporter):
        """Test exporter file extension property."""
        assert exporter.file_extension == ".sarif"

    def test_export_returns_valid_json(self, exporter, basic_report):
        """Test that export returns valid JSON."""
        result = exporter.export(basic_report)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_export_contains_sarif_schema(self, exporter, basic_report):
        """Test that export contains SARIF schema reference."""
        result = exporter.export(basic_report)
        parsed = json.loads(result)
        assert parsed["$schema"] == SARIF_SCHEMA

    def test_export_contains_sarif_version(self, exporter, basic_report):
        """Test that export contains correct SARIF version."""
        result = exporter.export(basic_report)
        parsed = json.loads(result)
        assert parsed["version"] == SARIF_VERSION

    def test_export_contains_runs(self, exporter, basic_report):
        """Test that export contains runs array."""
        result = exporter.export(basic_report)
        parsed = json.loads(result)
        assert "runs" in parsed
        assert isinstance(parsed["runs"], list)
        assert len(parsed["runs"]) == 1

    def test_export_contains_tool_info(self, exporter, basic_report):
        """Test that export contains tool information."""
        result = exporter.export(basic_report)
        parsed = json.loads(result)
        tool = parsed["runs"][0]["tool"]
        driver = tool["driver"]

        assert driver["name"] == TOOL_NAME
        assert driver["version"] == TOOL_VERSION
        assert "informationUri" in driver

    def test_export_contains_invocations(self, exporter, basic_report):
        """Test that export contains invocation information."""
        result = exporter.export(basic_report)
        parsed = json.loads(result)
        invocations = parsed["runs"][0]["invocations"]

        assert isinstance(invocations, list)
        assert len(invocations) == 1
        assert invocations[0]["executionSuccessful"] is True

    def test_export_with_findings(self, exporter, basic_report, finding_with_fix):
        """Test export with findings."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)

        # Check rules
        rules = parsed["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "MEILI-S001"
        assert rules[0]["shortDescription"]["text"] == "Wildcard searchable attributes"

        # Check results
        results = parsed["runs"][0]["results"]
        assert len(results) == 1
        assert results[0]["ruleId"] == "MEILI-S001"

    def test_severity_mapping_critical(self, exporter, basic_report):
        """Test critical severity maps to error."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.CRITICAL,
                title="Test finding",
                description="Test description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        result_entry = parsed["runs"][0]["results"][0]

        assert result_entry["level"] == "error"

    def test_severity_mapping_warning(self, exporter, basic_report):
        """Test warning severity maps to warning."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="Test finding",
                description="Test description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        result_entry = parsed["runs"][0]["results"][0]

        assert result_entry["level"] == "warning"

    def test_severity_mapping_suggestion(self, exporter, basic_report):
        """Test suggestion severity maps to note."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.SUGGESTION,
                title="Test finding",
                description="Test description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        result_entry = parsed["runs"][0]["results"][0]

        assert result_entry["level"] == "note"

    def test_severity_mapping_info(self, exporter, basic_report):
        """Test info severity maps to none."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.INFO,
                title="Test finding",
                description="Test description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        result_entry = parsed["runs"][0]["results"][0]

        assert result_entry["level"] == "none"

    def test_export_includes_logical_location(
        self, exporter, basic_report, finding_with_fix
    ):
        """Test that findings include logical locations."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        location = parsed["runs"][0]["results"][0]["locations"][0]

        assert "logicalLocations" in location
        assert location["logicalLocations"][0]["name"] == "products"
        assert (
            "indexes/products/settings"
            in location["logicalLocations"][0]["fullyQualifiedName"]
        )

    def test_export_global_finding_location(self, exporter, basic_report):
        """Test global findings have correct location."""
        basic_report.global_findings = [
            Finding(
                id="TEST-001",
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="Test finding",
                description="Test description",
                impact="Test impact",
            ),
        ]

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        location = parsed["runs"][0]["results"][0]["locations"][0]

        assert location["logicalLocations"][0]["name"] == "global"
        assert (
            "instance/global" in location["logicalLocations"][0]["fullyQualifiedName"]
        )

    def test_export_includes_fix(self, exporter, basic_report, finding_with_fix):
        """Test that fixes are included when enabled."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        result_entry = parsed["runs"][0]["results"][0]

        assert "fixes" in result_entry
        assert len(result_entry["fixes"]) == 1
        assert (
            "PATCH /indexes/products/settings"
            in result_entry["fixes"][0]["description"]["text"]
        )

    def test_export_without_fixes(self, exporter, basic_report, finding_with_fix):
        """Test export without fixes when disabled."""
        exporter_no_fix = SarifExporter(include_fixes=False)
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter_no_fix.export(basic_report)
        parsed = json.loads(result)
        result_entry = parsed["runs"][0]["results"][0]

        assert "fixes" not in result_entry

    def test_export_includes_current_value(
        self, exporter, basic_report, finding_with_fix
    ):
        """Test that current values are included in properties."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        properties = parsed["runs"][0]["results"][0]["properties"]

        assert "currentValue" in properties
        assert properties["currentValue"] == ["*"]

    def test_export_includes_recommended_value(
        self, exporter, basic_report, finding_with_fix
    ):
        """Test that recommended values are included in properties."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        properties = parsed["runs"][0]["results"][0]["properties"]

        assert "recommendedValue" in properties
        assert properties["recommendedValue"] == ["title", "description"]

    def test_export_includes_help_uri(self, exporter, basic_report, finding_with_fix):
        """Test that help URIs are included when references exist."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        rule = parsed["runs"][0]["tool"]["driver"]["rules"][0]

        assert rule["helpUri"] == "https://docs.meilisearch.com/"

    def test_export_deduplicates_rules(self, exporter, basic_report):
        """Test that duplicate rule IDs are deduplicated."""
        finding1 = Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Wildcard searchable attributes",
            description="First instance",
            impact="Poor search performance",
            index_uid="products",
        )
        finding2 = Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Wildcard searchable attributes",
            description="Second instance",
            impact="Poor search performance",
            index_uid="orders",
        )

        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding1],
        )
        basic_report.indexes["orders"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 500},
            findings=[finding2],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        rules = parsed["runs"][0]["tool"]["driver"]["rules"]

        # Should have one rule, two results
        assert len(rules) == 1
        assert len(parsed["runs"][0]["results"]) == 2

    def test_export_writes_to_file(self, exporter, basic_report):
        """Test that export writes to file when path provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "results.sarif"
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
        parsed = json.loads(result)

        assert parsed["version"] == SARIF_VERSION
        assert len(parsed["runs"][0]["results"]) == 0

    def test_export_pascal_case_conversion(self, exporter):
        """Test PascalCase conversion for rule names."""
        assert (
            exporter._to_pascal_case("wildcard searchable attributes")
            == "WildcardSearchableAttributes"
        )
        assert exporter._to_pascal_case("id-fields-in-search") == "IdFieldsInSearch"
        assert exporter._to_pascal_case("test_case_here") == "TestCaseHere"

    def test_export_message_contains_description(
        self, exporter, basic_report, finding_with_fix
    ):
        """Test that result message contains finding description."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        message = parsed["runs"][0]["results"][0]["message"]["text"]

        assert "All fields are searchable by default." in message
        assert "products" in message
        assert "Poor search performance" in message

    def test_export_rule_tags(self, exporter, basic_report, finding_with_fix):
        """Test that rules have appropriate tags."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[finding_with_fix],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)
        rule = parsed["runs"][0]["tool"]["driver"]["rules"][0]

        assert "tags" in rule["properties"]
        assert "schema" in rule["properties"]["tags"]
        assert "critical" in rule["properties"]["tags"]

    def test_export_multiple_indexes(self, exporter, basic_report):
        """Test export with multiple indexes."""
        basic_report.indexes["products"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 1000},
            findings=[
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Wildcard searchable",
                    description="Test",
                    impact="Test",
                    index_uid="products",
                ),
            ],
        )
        basic_report.indexes["orders"] = IndexAnalysis(
            metadata={"primary_key": "id", "document_count": 500},
            findings=[
                Finding(
                    id="MEILI-D001",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Large documents",
                    description="Test",
                    impact="Test",
                    index_uid="orders",
                ),
            ],
        )

        result = exporter.export(basic_report)
        parsed = json.loads(result)

        assert len(parsed["runs"][0]["results"]) == 2
        assert len(parsed["runs"][0]["tool"]["driver"]["rules"]) == 2
