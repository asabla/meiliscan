"""Tests for HistoricalAnalyzer and comparison models."""

from datetime import datetime, timedelta

import pytest

from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.models.comparison import (
    ChangeType,
    ComparisonReport,
    MetricChange,
    TrendDirection,
)
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.report import (
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)


class TestMetricChange:
    """Tests for MetricChange calculation."""

    def test_calculate_increase(self):
        """Test metric increase calculation."""
        change = MetricChange.calculate("test", 100, 150, higher_is_better=True)
        assert change.old_value == 100
        assert change.new_value == 150
        assert change.change == 50
        assert change.change_percent == 50.0
        assert change.trend == TrendDirection.UP

    def test_calculate_decrease(self):
        """Test metric decrease calculation."""
        change = MetricChange.calculate("test", 100, 80, higher_is_better=True)
        assert change.change == -20
        assert change.change_percent == -20.0
        assert change.trend == TrendDirection.DOWN

    def test_calculate_no_change(self):
        """Test metric with no change."""
        change = MetricChange.calculate("test", 100, 100)
        assert change.change == 0
        assert change.trend == TrendDirection.STABLE

    def test_calculate_with_none_values(self):
        """Test calculation with None values."""
        change = MetricChange.calculate("test", None, 100)
        assert change.old_value is None
        assert change.new_value == 100
        assert change.change == 0

    def test_calculate_from_zero(self):
        """Test calculation from zero baseline."""
        change = MetricChange.calculate("test", 0, 100)
        assert change.change == 100
        assert change.change_percent is None  # Division by zero


class TestHistoricalAnalyzer:
    """Tests for HistoricalAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> HistoricalAnalyzer:
        """Create analyzer instance."""
        return HistoricalAnalyzer()

    @pytest.fixture
    def old_report(self) -> AnalysisReport:
        """Create an older baseline report."""
        report = AnalysisReport(
            generated_at=datetime.utcnow() - timedelta(days=7),
            source=SourceInfo(type="instance", url="http://localhost:7700"),
            summary=AnalysisSummary(
                total_indexes=2,
                total_documents=1000,
                health_score=70,
                critical_issues=2,
                warnings=5,
                suggestions=3,
            ),
        )
        report.indexes["products"] = IndexAnalysis(
            metadata={"document_count": 800, "primary_key": "id"},
            settings={"current": {"searchableAttributes": ["*"]}},
            statistics={"field_count": 10},
            findings=[
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Wildcard searchableAttributes",
                    description="Test",
                    impact="Test",
                    index_uid="products",
                ),
            ],
        )
        report.indexes["orders"] = IndexAnalysis(
            metadata={"document_count": 200, "primary_key": "id"},
            settings={"current": {}},
            statistics={"field_count": 5},
            findings=[],
        )
        return report

    @pytest.fixture
    def new_report_improved(self) -> AnalysisReport:
        """Create a newer report with improvements."""
        report = AnalysisReport(
            generated_at=datetime.utcnow(),
            source=SourceInfo(type="instance", url="http://localhost:7700"),
            summary=AnalysisSummary(
                total_indexes=2,
                total_documents=1500,
                health_score=85,
                critical_issues=0,
                warnings=3,
                suggestions=2,
            ),
        )
        report.indexes["products"] = IndexAnalysis(
            metadata={"document_count": 1200, "primary_key": "id"},
            settings={"current": {"searchableAttributes": ["title", "description"]}},
            statistics={"field_count": 10},
            findings=[],  # S001 resolved
        )
        report.indexes["orders"] = IndexAnalysis(
            metadata={"document_count": 300, "primary_key": "id"},
            settings={"current": {}},
            statistics={"field_count": 5},
            findings=[],
        )
        return report

    @pytest.fixture
    def new_report_degraded(self) -> AnalysisReport:
        """Create a newer report with degradations."""
        report = AnalysisReport(
            generated_at=datetime.utcnow(),
            source=SourceInfo(type="instance", url="http://localhost:7700"),
            summary=AnalysisSummary(
                total_indexes=3,
                total_documents=2000,
                health_score=55,
                critical_issues=4,
                warnings=8,
                suggestions=5,
            ),
        )
        report.indexes["products"] = IndexAnalysis(
            metadata={"document_count": 1500, "primary_key": "id"},
            settings={"current": {"searchableAttributes": ["*"]}},
            statistics={"field_count": 15},
            findings=[
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Wildcard searchableAttributes",
                    description="Test",
                    impact="Test",
                    index_uid="products",
                ),
                Finding(
                    id="MEILI-D001",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Large documents",
                    description="Test",
                    impact="Test",
                    index_uid="products",
                ),
            ],
        )
        report.indexes["orders"] = IndexAnalysis(
            metadata={"document_count": 300, "primary_key": "id"},
            settings={"current": {}},
            statistics={"field_count": 5},
            findings=[],
        )
        report.indexes["customers"] = IndexAnalysis(
            metadata={"document_count": 200, "primary_key": "id"},
            settings={"current": {"searchableAttributes": ["*"]}},
            statistics={"field_count": 8},
            findings=[
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Wildcard searchableAttributes",
                    description="Test",
                    impact="Test",
                    index_uid="customers",
                ),
            ],
        )
        return report

    def test_compare_basic(self, analyzer, old_report, new_report_improved):
        """Test basic comparison returns ComparisonReport."""
        result = analyzer.compare(old_report, new_report_improved)
        assert isinstance(result, ComparisonReport)
        assert result.summary is not None

    def test_compare_detects_improvement(
        self, analyzer, old_report, new_report_improved
    ):
        """Test that improvement in health score is detected."""
        result = analyzer.compare(old_report, new_report_improved)
        assert result.summary.health_score.old_value == 70
        assert result.summary.health_score.new_value == 85
        assert result.summary.health_score.trend == TrendDirection.UP
        assert result.summary.overall_trend == TrendDirection.UP

    def test_compare_detects_degradation(
        self, analyzer, old_report, new_report_degraded
    ):
        """Test that degradation in health score is detected."""
        result = analyzer.compare(old_report, new_report_degraded)
        assert result.summary.health_score.old_value == 70
        assert result.summary.health_score.new_value == 55
        assert result.summary.health_score.trend == TrendDirection.DOWN
        assert result.summary.overall_trend == TrendDirection.DOWN

    def test_compare_detects_new_indexes(
        self, analyzer, old_report, new_report_degraded
    ):
        """Test detection of newly added indexes."""
        result = analyzer.compare(old_report, new_report_degraded)
        assert "customers" in result.summary.indexes_added
        assert len(result.summary.indexes_added) == 1

    def test_compare_detects_removed_indexes(
        self, analyzer, old_report, new_report_improved
    ):
        """Test detection of removed indexes when present."""
        # Modify new_report to remove an index
        new_report = new_report_improved
        del new_report.indexes["orders"]
        new_report.summary.total_indexes = 1

        result = analyzer.compare(old_report, new_report)
        assert "orders" in result.summary.indexes_removed

    def test_compare_detects_resolved_findings(
        self, analyzer, old_report, new_report_improved
    ):
        """Test detection of resolved findings."""
        result = analyzer.compare(old_report, new_report_improved)

        resolved = [
            fc for fc in result.finding_changes if fc.change_type == ChangeType.REMOVED
        ]
        assert len(resolved) == 1
        assert resolved[0].finding.id == "MEILI-S001"

    def test_compare_detects_new_findings(
        self, analyzer, old_report, new_report_degraded
    ):
        """Test detection of new findings."""
        result = analyzer.compare(old_report, new_report_degraded)

        new_findings = [
            fc for fc in result.finding_changes if fc.change_type == ChangeType.ADDED
        ]
        # D001 is new, and S001 on customers is new
        new_ids = {fc.finding.id for fc in new_findings}
        assert "MEILI-D001" in new_ids

    def test_compare_critical_issues_change(
        self, analyzer, old_report, new_report_improved
    ):
        """Test critical issues count change."""
        result = analyzer.compare(old_report, new_report_improved)
        assert result.summary.critical_issues.old_value == 2
        assert result.summary.critical_issues.new_value == 0
        assert result.summary.critical_issues.trend == TrendDirection.DOWN

    def test_compare_document_count_change(
        self, analyzer, old_report, new_report_improved
    ):
        """Test document count change detection."""
        result = analyzer.compare(old_report, new_report_improved)
        assert result.summary.total_documents.old_value == 1000
        assert result.summary.total_documents.new_value == 1500
        assert result.summary.total_documents.change == 500

    def test_compare_generates_recommendations(
        self, analyzer, old_report, new_report_degraded
    ):
        """Test that recommendations are generated."""
        result = analyzer.compare(old_report, new_report_degraded)
        assert len(result.recommendations) > 0

    def test_compare_improvement_areas(self, analyzer, old_report, new_report_improved):
        """Test improvement areas are identified."""
        result = analyzer.compare(old_report, new_report_improved)
        assert len(result.summary.improvement_areas) > 0
        # Should mention resolved critical issues
        assert any(
            "critical" in area.lower() for area in result.summary.improvement_areas
        )

    def test_compare_degradation_areas(self, analyzer, old_report, new_report_degraded):
        """Test degradation areas are identified."""
        result = analyzer.compare(old_report, new_report_degraded)
        assert len(result.summary.degradation_areas) > 0

    def test_compare_time_between_reports(
        self, analyzer, old_report, new_report_improved
    ):
        """Test time difference is calculated."""
        result = analyzer.compare(old_report, new_report_improved)
        assert result.summary.time_between  # Should be "7 days" or similar

    def test_compare_index_settings_change(
        self, analyzer, old_report, new_report_improved
    ):
        """Test detection of settings changes within an index."""
        result = analyzer.compare(old_report, new_report_improved)

        products_change = result.index_changes.get("products")
        assert products_change is not None
        assert products_change.settings_changed is True
        assert "searchableAttributes" in products_change.settings_diff

    def test_compare_index_document_growth(
        self, analyzer, old_report, new_report_improved
    ):
        """Test document count change within an index."""
        result = analyzer.compare(old_report, new_report_improved)

        products_change = result.index_changes.get("products")
        assert products_change is not None
        assert products_change.document_count.old_value == 800
        assert products_change.document_count.new_value == 1200

    def test_compare_to_dict(self, analyzer, old_report, new_report_improved):
        """Test comparison report serialization."""
        result = analyzer.compare(old_report, new_report_improved)
        data = result.to_dict()

        assert "summary" in data
        assert "index_changes" in data
        assert "finding_changes" in data
        assert "recommendations" in data


class TestComparisonReport:
    """Tests for ComparisonReport model."""

    def test_to_dict_serialization(self):
        """Test that ComparisonReport serializes correctly."""
        from meiliscan.models.comparison import ComparisonSummary

        summary = ComparisonSummary(
            old_report_date=datetime.utcnow() - timedelta(days=1),
            new_report_date=datetime.utcnow(),
            time_between="1 day",
            health_score=MetricChange.calculate("health_score", 70, 80),
            total_documents=MetricChange.calculate("total_documents", 1000, 1500),
            total_indexes=MetricChange.calculate("total_indexes", 2, 2),
            critical_issues=MetricChange.calculate("critical_issues", 2, 0),
            warnings=MetricChange.calculate("warnings", 5, 3),
            suggestions=MetricChange.calculate("suggestions", 3, 2),
        )

        report = ComparisonReport(
            old_source={"type": "instance", "url": "http://localhost:7700"},
            new_source={"type": "instance", "url": "http://localhost:7700"},
            summary=summary,
        )

        data = report.to_dict()
        assert "summary" in data
        assert "old_source" in data
        assert "new_source" in data

    def test_comparison_report_requires_summary(self):
        """Test that ComparisonReport requires a summary."""
        with pytest.raises(Exception):
            ComparisonReport(
                old_source={"type": "instance"},
                new_source={"type": "instance"},
                summary=None,
            )

    def test_comparison_summary_fields(self):
        """Test ComparisonSummary has all required fields."""
        from meiliscan.models.comparison import ComparisonSummary

        summary = ComparisonSummary(
            old_report_date=datetime.utcnow() - timedelta(days=1),
            new_report_date=datetime.utcnow(),
            time_between="1 day",
            health_score=MetricChange.calculate("health_score", 70, 80),
            total_documents=MetricChange.calculate("total_documents", 1000, 1500),
            total_indexes=MetricChange.calculate("total_indexes", 2, 2),
            critical_issues=MetricChange.calculate("critical_issues", 2, 0),
            warnings=MetricChange.calculate("warnings", 5, 3),
            suggestions=MetricChange.calculate("suggestions", 3, 2),
        )

        assert summary.overall_trend == TrendDirection.STABLE  # Default
        assert summary.indexes_added == []
        assert summary.indexes_removed == []


class TestTimeFormatting:
    """Tests for time difference formatting."""

    @pytest.fixture
    def analyzer(self) -> HistoricalAnalyzer:
        return HistoricalAnalyzer()

    def test_format_days(self, analyzer):
        """Test formatting multiple days."""
        old = datetime.utcnow() - timedelta(days=5)
        new = datetime.utcnow()
        result = analyzer._format_time_difference(old, new)
        assert result == "5 days"

    def test_format_single_day(self, analyzer):
        """Test formatting single day."""
        old = datetime.utcnow() - timedelta(days=1)
        new = datetime.utcnow()
        result = analyzer._format_time_difference(old, new)
        assert result == "1 day"

    def test_format_hours(self, analyzer):
        """Test formatting hours."""
        old = datetime.utcnow() - timedelta(hours=5)
        new = datetime.utcnow()
        result = analyzer._format_time_difference(old, new)
        assert result == "5 hours"

    def test_format_single_hour(self, analyzer):
        """Test formatting single hour."""
        old = datetime.utcnow() - timedelta(hours=1)
        new = datetime.utcnow()
        result = analyzer._format_time_difference(old, new)
        assert result == "1 hour"

    def test_format_minutes(self, analyzer):
        """Test formatting minutes."""
        old = datetime.utcnow() - timedelta(minutes=30)
        new = datetime.utcnow()
        result = analyzer._format_time_difference(old, new)
        assert result == "30 minutes"

    def test_format_less_than_minute(self, analyzer):
        """Test formatting very short time."""
        old = datetime.utcnow() - timedelta(seconds=30)
        new = datetime.utcnow()
        result = analyzer._format_time_difference(old, new)
        assert result == "less than a minute"
