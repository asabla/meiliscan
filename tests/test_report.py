"""Tests for Report models."""

import pytest
from datetime import datetime

from meilisearch_analyzer.models.finding import Finding, FindingCategory, FindingSeverity
from meilisearch_analyzer.models.index import IndexData, IndexSettings, IndexStats
from meilisearch_analyzer.models.report import (
    ActionPlan,
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)


class TestSourceInfo:
    """Tests for SourceInfo model."""

    def test_instance_source(self):
        """Test creating an instance source."""
        source = SourceInfo(
            type="instance",
            url="http://localhost:7700",
            meilisearch_version="1.12.0",
        )
        assert source.type == "instance"
        assert source.url == "http://localhost:7700"
        assert source.meilisearch_version == "1.12.0"
        assert source.dump_path is None

    def test_dump_source(self):
        """Test creating a dump source."""
        source = SourceInfo(
            type="dump",
            dump_path="/path/to/dump.dump",
            dump_date=datetime(2024, 1, 1),
        )
        assert source.type == "dump"
        assert source.dump_path == "/path/to/dump.dump"
        assert source.url is None


class TestAnalysisSummary:
    """Tests for AnalysisSummary model."""

    def test_default_summary(self):
        """Test default summary values."""
        summary = AnalysisSummary()
        assert summary.total_indexes == 0
        assert summary.total_documents == 0
        assert summary.health_score == 100
        assert summary.critical_issues == 0
        assert summary.warnings == 0

    def test_custom_summary(self):
        """Test custom summary values."""
        summary = AnalysisSummary(
            total_indexes=5,
            total_documents=100000,
            health_score=75,
            critical_issues=2,
            warnings=5,
            suggestions=10,
        )
        assert summary.total_indexes == 5
        assert summary.health_score == 75


class TestAnalysisReport:
    """Tests for AnalysisReport model."""

    @pytest.fixture
    def sample_report(self) -> AnalysisReport:
        """Create a sample report for testing."""
        return AnalysisReport(
            source=SourceInfo(
                type="instance",
                url="http://localhost:7700",
                meilisearch_version="1.12.0",
            ),
        )

    def test_report_creation(self, sample_report):
        """Test creating a report."""
        assert sample_report.source.type == "instance"
        assert sample_report.version == "1.0.0"
        assert sample_report.generated_at is not None

    def test_add_index(self, sample_report):
        """Test adding an index to the report."""
        index = IndexData(
            uid="products",
            primaryKey="id",
            settings=IndexSettings(searchableAttributes=["title"]),
            stats=IndexStats(
                numberOfDocuments=1000,
                fieldDistribution={"id": 1000, "title": 1000},
            ),
        )
        
        sample_report.add_index(index)
        
        assert "products" in sample_report.indexes
        assert sample_report.indexes["products"].metadata["document_count"] == 1000
        assert sample_report.indexes["products"].metadata["primary_key"] == "id"

    def test_add_finding_to_index(self, sample_report):
        """Test adding a finding for a specific index."""
        # First add the index
        index = IndexData(uid="products")
        sample_report.add_index(index)
        
        # Then add a finding for that index
        finding = Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Test finding",
            description="Test description",
            impact="Test impact",
            index_uid="products",
        )
        
        sample_report.add_finding(finding)
        
        assert len(sample_report.indexes["products"].findings) == 1
        assert sample_report.indexes["products"].findings[0].id == "MEILI-S001"

    def test_add_global_finding(self, sample_report):
        """Test adding a global finding."""
        finding = Finding(
            id="MEILI-G001",
            category=FindingCategory.PERFORMANCE,
            severity=FindingSeverity.WARNING,
            title="Global finding",
            description="Test description",
            impact="Test impact",
        )
        
        sample_report.add_finding(finding)
        
        assert len(sample_report.global_findings) == 1
        assert sample_report.global_findings[0].id == "MEILI-G001"

    def test_calculate_summary(self, sample_report):
        """Test summary calculation."""
        # Add indexes
        for uid in ["products", "orders"]:
            index = IndexData(
                uid=uid,
                stats=IndexStats(numberOfDocuments=500),
            )
            sample_report.add_index(index)
        
        # Add findings
        findings = [
            Finding(
                id="F1",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.CRITICAL,
                title="Critical",
                description="Test",
                impact="Test",
                index_uid="products",
            ),
            Finding(
                id="F2",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.WARNING,
                title="Warning",
                description="Test",
                impact="Test",
                index_uid="orders",
            ),
            Finding(
                id="F3",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.SUGGESTION,
                title="Suggestion",
                description="Test",
                impact="Test",
            ),
        ]
        
        for finding in findings:
            sample_report.add_finding(finding)
        
        sample_report.calculate_summary()
        
        assert sample_report.summary.total_indexes == 2
        assert sample_report.summary.total_documents == 1000
        assert sample_report.summary.critical_issues == 1
        assert sample_report.summary.warnings == 1
        assert sample_report.summary.suggestions == 1

    def test_get_all_findings(self, sample_report):
        """Test getting all findings."""
        index = IndexData(uid="test")
        sample_report.add_index(index)
        
        # Add index finding
        sample_report.add_finding(Finding(
            id="F1",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.WARNING,
            title="Index finding",
            description="Test",
            impact="Test",
            index_uid="test",
        ))
        
        # Add global finding
        sample_report.add_finding(Finding(
            id="F2",
            category=FindingCategory.PERFORMANCE,
            severity=FindingSeverity.INFO,
            title="Global finding",
            description="Test",
            impact="Test",
        ))
        
        all_findings = sample_report.get_all_findings()
        assert len(all_findings) == 2
        assert {f.id for f in all_findings} == {"F1", "F2"}

    def test_to_dict(self, sample_report):
        """Test converting report to dictionary."""
        data = sample_report.to_dict()
        
        assert "source" in data
        assert "summary" in data
        assert "indexes" in data
        assert "global_findings" in data
        assert "action_plan" in data
        assert data["version"] == "1.0.0"


class TestActionPlan:
    """Tests for ActionPlan model."""

    def test_default_action_plan(self):
        """Test default action plan."""
        plan = ActionPlan()
        assert plan.priority_order == []
        assert plan.estimated_impact == {}

    def test_custom_action_plan(self):
        """Test custom action plan."""
        plan = ActionPlan(
            priority_order=["MEILI-S001", "MEILI-S002"],
            estimated_impact={
                "index_size_reduction": "~30%",
                "search_latency_improvement": "~10%",
            },
        )
        assert len(plan.priority_order) == 2
        assert "index_size_reduction" in plan.estimated_impact
