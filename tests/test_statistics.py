"""Tests for the statistics module."""

from datetime import datetime, timezone

import pytest

from meiliscan.core.statistics import (
    calculate_configuration_coverage,
    calculate_index_statistics,
    calculate_statistics,
    identify_performance_opportunities,
)
from meiliscan.models.finding import Finding, FindingCategory, FindingSeverity
from meiliscan.models.index import IndexSettings, TypoToleranceSettings
from meiliscan.models.report import (
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)
from meiliscan.models.statistics import (
    CollectionTiming,
    IndexStatistics,
    InstanceStatistics,
    PerformanceOpportunity,
)


# ============================================================================
# Configuration Coverage Tests
# ============================================================================


class TestCalculateConfigurationCoverage:
    """Tests for calculate_configuration_coverage function."""

    def test_default_settings_zero_coverage(self):
        """Test that default settings have 0% coverage."""
        settings = IndexSettings()

        flags, coverage = calculate_configuration_coverage(settings)

        assert coverage == 0
        assert flags["has_custom_searchable"] is False
        assert flags["has_custom_filterable"] is False
        assert flags["has_custom_sortable"] is False

    def test_custom_searchable_attributes(self):
        """Test custom searchable attributes increase coverage."""
        settings = IndexSettings(searchable_attributes=["title", "description"])

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_custom_searchable"] is True
        assert coverage > 0

    def test_custom_filterable_attributes(self):
        """Test custom filterable attributes increase coverage."""
        settings = IndexSettings(filterable_attributes=["category", "price"])

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_custom_filterable"] is True
        assert coverage > 0

    def test_custom_sortable_attributes(self):
        """Test custom sortable attributes increase coverage."""
        settings = IndexSettings(sortable_attributes=["created_at"])

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_custom_sortable"] is True
        assert coverage > 0

    def test_custom_ranking_rules(self):
        """Test custom ranking rules increase coverage."""
        settings = IndexSettings(ranking_rules=["words", "exactness", "typo"])

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_custom_ranking"] is True
        assert coverage > 0

    def test_stop_words(self):
        """Test stop words increase coverage."""
        settings = IndexSettings(stop_words=["the", "a", "an"])

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_stop_words"] is True
        assert coverage > 0

    def test_synonyms(self):
        """Test synonyms increase coverage."""
        settings = IndexSettings(synonyms={"car": ["automobile", "vehicle"]})

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_synonyms"] is True
        assert coverage > 0

    def test_typo_tolerance_disabled(self):
        """Test disabling typo tolerance counts as customization."""
        settings = IndexSettings(typo_tolerance=TypoToleranceSettings(enabled=False))

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_typo_config"] is True
        assert coverage > 0

    def test_typo_tolerance_disable_on_words(self):
        """Test typo tolerance disable_on_words counts as customization."""
        settings = IndexSettings(
            typo_tolerance=TypoToleranceSettings(disable_on_words=["API", "SDK"])
        )

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_typo_config"] is True

    def test_distinct_attribute(self):
        """Test distinct attribute increases coverage."""
        settings = IndexSettings(distinct_attribute="product_id")

        flags, coverage = calculate_configuration_coverage(settings)

        assert flags["has_distinct"] is True
        assert coverage > 0

    def test_fully_configured_settings(self):
        """Test fully configured settings have high coverage."""
        settings = IndexSettings(
            searchable_attributes=["title", "description"],
            filterable_attributes=["category"],
            sortable_attributes=["price"],
            ranking_rules=["words", "exactness"],
            stop_words=["the"],
            synonyms={"fast": ["quick"]},
            typo_tolerance=TypoToleranceSettings(enabled=False),
            distinct_attribute="id",
        )

        flags, coverage = calculate_configuration_coverage(settings)

        assert coverage == 100  # All 8 flags should be True
        assert all(flags.values())


# ============================================================================
# Index Statistics Tests
# ============================================================================


class TestCalculateIndexStatistics:
    """Tests for calculate_index_statistics function."""

    @pytest.fixture
    def basic_index_analysis(self) -> IndexAnalysis:
        """Create a basic index analysis for testing."""
        return IndexAnalysis(
            metadata={"document_count": 1000, "primary_key": "id"},
            settings={"current": {}},
            statistics={"field_count": 10},
            findings=[],
            sample_documents=[],
        )

    def test_basic_statistics(self, basic_index_analysis: IndexAnalysis):
        """Test basic statistics calculation."""
        stats = calculate_index_statistics("test-index", basic_index_analysis)

        assert stats.uid == "test-index"
        assert stats.document_count == 1000
        assert stats.field_count == 10
        assert stats.configuration_coverage == 0

    def test_statistics_with_findings(self):
        """Test statistics with various severity findings."""
        analysis = IndexAnalysis(
            metadata={"document_count": 500},
            settings={"current": {}},
            statistics={"field_count": 5},
            findings=[
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Critical Issue",
                    description="Test",
                    impact="Test",
                    index_uid="test",
                ),
                Finding(
                    id="MEILI-S002",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title="Warning Issue",
                    description="Test",
                    impact="Test",
                    index_uid="test",
                ),
                Finding(
                    id="MEILI-S003",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="Suggestion",
                    description="Test",
                    impact="Test",
                    index_uid="test",
                ),
            ],
            sample_documents=[],
        )

        stats = calculate_index_statistics("test", analysis)

        assert stats.critical_count == 1
        assert stats.warning_count == 1
        assert stats.suggestion_count == 1
        assert stats.total_issues == 3
        assert stats.has_issues is True

    def test_statistics_with_configured_settings(self):
        """Test statistics with configured settings."""
        analysis = IndexAnalysis(
            metadata={"document_count": 100},
            settings={
                "current": {
                    "searchableAttributes": ["title", "body"],
                    "filterableAttributes": ["category"],
                    "sortableAttributes": ["date"],
                }
            },
            statistics={"field_count": 5},
            findings=[],
            sample_documents=[],
        )

        stats = calculate_index_statistics("configured", analysis)

        assert stats.has_custom_searchable is True
        assert stats.has_custom_filterable is True
        assert stats.has_custom_sortable is True
        assert stats.configuration_coverage > 0


# ============================================================================
# Performance Opportunities Tests
# ============================================================================


class TestIdentifyPerformanceOpportunities:
    """Tests for identify_performance_opportunities function."""

    def test_empty_findings(self):
        """Test with no findings."""
        opportunities = identify_performance_opportunities([])

        assert opportunities == []

    def test_info_findings_excluded(self):
        """Test that INFO severity findings are excluded."""
        findings = [
            Finding(
                id="MEILI-TEST",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.INFO,
                title="Info Finding",
                description="Test",
                impact="Test",
                index_uid="test",
            ),
        ]

        opportunities = identify_performance_opportunities(findings)

        assert opportunities == []

    def test_critical_finding_creates_opportunity(self):
        """Test that critical findings create opportunities."""
        findings = [
            Finding(
                id="MEILI-S001",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.CRITICAL,
                title="Wildcard searchableAttributes",
                description="Using wildcard searchableAttributes",
                impact="Performance impact",
                index_uid="products",
            ),
        ]

        opportunities = identify_performance_opportunities(findings)

        assert len(opportunities) == 1
        assert opportunities[0].id == "MEILI-S001"
        assert opportunities[0].estimated_impact == "high"
        assert "products" in opportunities[0].affected_indexes

    def test_groups_findings_by_id(self):
        """Test that findings are grouped by ID."""
        findings = [
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
                id="MEILI-S001",
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.CRITICAL,
                title="Wildcard searchableAttributes",
                description="Test",
                impact="Test",
                index_uid="articles",
            ),
        ]

        opportunities = identify_performance_opportunities(findings)

        assert len(opportunities) == 1
        assert set(opportunities[0].affected_indexes) == {"products", "articles"}

    def test_sorted_by_impact(self):
        """Test opportunities are sorted by impact (high first)."""
        findings = [
            Finding(
                id="MEILI-S006",  # Low impact (synonyms)
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.SUGGESTION,
                title="Missing synonyms",
                description="Test",
                impact="Test",
                index_uid="test",
            ),
            Finding(
                id="MEILI-S001",  # High impact (wildcard searchable)
                category=FindingCategory.SCHEMA,
                severity=FindingSeverity.CRITICAL,
                title="Wildcard searchableAttributes",
                description="Test",
                impact="Test",
                index_uid="test",
            ),
        ]

        opportunities = identify_performance_opportunities(findings)

        assert len(opportunities) == 2
        assert opportunities[0].estimated_impact == "high"
        assert opportunities[1].estimated_impact == "low"


# ============================================================================
# Calculate Statistics Tests
# ============================================================================


class TestCalculateStatistics:
    """Tests for calculate_statistics function."""

    @pytest.fixture
    def sample_report(self) -> AnalysisReport:
        """Create a sample analysis report."""
        return AnalysisReport(
            generated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            source=SourceInfo(type="instance", url="http://localhost:7700"),
            version="1.0.0",
            indexes={
                "products": IndexAnalysis(
                    metadata={"document_count": 1000},
                    settings={
                        "current": {
                            "searchableAttributes": ["title", "description"],
                            "filterableAttributes": ["category"],
                        }
                    },
                    statistics={"field_count": 10},
                    findings=[
                        Finding(
                            id="MEILI-S005",
                            category=FindingCategory.SCHEMA,
                            severity=FindingSeverity.WARNING,
                            title="Missing stop words",
                            description="Test",
                            impact="Test",
                            index_uid="products",
                        ),
                    ],
                    sample_documents=[],
                ),
                "articles": IndexAnalysis(
                    metadata={"document_count": 500},
                    settings={"current": {}},
                    statistics={"field_count": 5},
                    findings=[
                        Finding(
                            id="MEILI-S001",
                            category=FindingCategory.SCHEMA,
                            severity=FindingSeverity.CRITICAL,
                            title="Wildcard searchableAttributes",
                            description="Test",
                            impact="Test",
                            index_uid="articles",
                        ),
                    ],
                    sample_documents=[],
                ),
            },
            global_findings=[],
            summary=AnalysisSummary(
                total_indexes=2,
                total_documents=1500,
                critical_issues=1,
                warnings=1,
                suggestions=0,
                info_items=0,
                configuration_coverage=25,
            ),
        )

    def test_calculate_statistics_basic(self, sample_report: AnalysisReport):
        """Test basic statistics calculation."""
        stats = calculate_statistics(sample_report)

        assert stats.total_indexes == 2
        assert stats.total_documents == 1500
        assert stats.total_fields == 15  # 10 + 5

    def test_calculate_statistics_configuration_counts(
        self, sample_report: AnalysisReport
    ):
        """Test configuration coverage counts."""
        stats = calculate_statistics(sample_report)

        # products has custom searchable/filterable, articles has defaults
        assert stats.indexes_with_custom_searchable == 1
        assert stats.indexes_with_custom_filterable == 1

    def test_calculate_statistics_with_timing(self, sample_report: AnalysisReport):
        """Test statistics with collection timing."""
        timing = CollectionTiming(
            connect_ms=50.0,
            version_ms=10.0,
            stats_ms=20.0,
            indexes_list_ms=30.0,
            per_index_avg_ms=100.0,
            total_ms=500.0,
        )

        stats = calculate_statistics(sample_report, collection_timing=timing)

        assert stats.collection_timing is not None
        assert stats.collection_timing.total_ms == 500.0

    def test_calculate_statistics_with_size_info(self, sample_report: AnalysisReport):
        """Test statistics with database size info."""
        stats = calculate_statistics(
            sample_report,
            database_size_bytes=1000000,  # 1MB
            used_size_bytes=800000,  # 800KB
        )

        assert stats.database_size_bytes == 1000000
        assert stats.used_size_bytes == 800000
        assert stats.fragmentation_percent == pytest.approx(20.0)  # 200KB/1MB = 20%

    def test_calculate_statistics_performance_opportunities(
        self, sample_report: AnalysisReport
    ):
        """Test that performance opportunities are identified."""
        stats = calculate_statistics(sample_report)

        # Should have opportunities for MEILI-S001 (high) and MEILI-S005 (medium)
        assert len(stats.performance_opportunities) >= 1

    def test_calculate_statistics_issue_totals(self, sample_report: AnalysisReport):
        """Test issue totals are calculated correctly."""
        stats = calculate_statistics(sample_report)

        assert stats.total_critical == 1
        assert stats.total_warnings == 1
        assert stats.total_suggestions == 0

    def test_calculate_statistics_empty_report(self):
        """Test statistics for empty report."""
        report = AnalysisReport(
            generated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            source=SourceInfo(type="instance", url="http://localhost:7700"),
            version="1.0.0",
            indexes={},
            global_findings=[],
            summary=AnalysisSummary(
                total_indexes=0,
                total_documents=0,
                critical_issues=0,
                warnings=0,
                suggestions=0,
                info_items=0,
                configuration_coverage=0,
            ),
        )

        stats = calculate_statistics(report)

        assert stats.total_indexes == 0
        assert stats.total_documents == 0
        assert stats.overall_coverage_percent == 0


# ============================================================================
# Statistics Models Tests
# ============================================================================


class TestCollectionTiming:
    """Tests for CollectionTiming model."""

    def test_to_display_dict(self):
        """Test conversion to display format."""
        timing = CollectionTiming(
            connect_ms=50.5,
            version_ms=10.2,
            stats_ms=20.8,
            indexes_list_ms=30.1,
            per_index_avg_ms=100.9,
            total_ms=500.5,
        )

        display = timing.to_display_dict()

        assert display["connect"] == "50ms"
        assert display["total"] == "500ms"


class TestIndexStatistics:
    """Tests for IndexStatistics model."""

    def test_total_issues(self):
        """Test total_issues property."""
        stats = IndexStatistics(
            uid="test",
            critical_count=2,
            warning_count=3,
            suggestion_count=5,
            info_count=10,
        )

        assert stats.total_issues == 10  # Excludes info

    def test_has_issues_true(self):
        """Test has_issues when there are critical/warning issues."""
        stats = IndexStatistics(uid="test", critical_count=1)
        assert stats.has_issues is True

        stats = IndexStatistics(uid="test", warning_count=1)
        assert stats.has_issues is True

    def test_has_issues_false(self):
        """Test has_issues when there are only suggestions/info."""
        stats = IndexStatistics(uid="test", suggestion_count=5, info_count=10)
        assert stats.has_issues is False


class TestPerformanceOpportunity:
    """Tests for PerformanceOpportunity model."""

    def test_impact_order(self):
        """Test impact_order property."""
        high = PerformanceOpportunity(
            id="1",
            category="schema",
            title="High",
            description="Test",
            estimated_impact="high",
            estimated_improvement="Test",
        )
        medium = PerformanceOpportunity(
            id="2",
            category="schema",
            title="Medium",
            description="Test",
            estimated_impact="medium",
            estimated_improvement="Test",
        )
        low = PerformanceOpportunity(
            id="3",
            category="schema",
            title="Low",
            description="Test",
            estimated_impact="low",
            estimated_improvement="Test",
        )

        assert high.impact_order < medium.impact_order < low.impact_order


class TestInstanceStatistics:
    """Tests for InstanceStatistics model."""

    @pytest.fixture
    def sample_stats(self) -> InstanceStatistics:
        """Create sample instance statistics."""
        return InstanceStatistics(
            total_indexes=3,
            indexes_with_custom_searchable=2,
            indexes_with_custom_filterable=1,
            indexes_with_custom_sortable=1,
            indexes_with_custom_ranking=0,
            indexes_with_stop_words=1,
            indexes_with_synonyms=0,
            performance_opportunities=[
                PerformanceOpportunity(
                    id="1",
                    category="schema",
                    title="High Impact",
                    description="Test",
                    estimated_impact="high",
                    estimated_improvement="Test",
                ),
                PerformanceOpportunity(
                    id="2",
                    category="schema",
                    title="Medium Impact",
                    description="Test",
                    estimated_impact="medium",
                    estimated_improvement="Test",
                ),
                PerformanceOpportunity(
                    id="3",
                    category="schema",
                    title="Low Impact",
                    description="Test",
                    estimated_impact="low",
                    estimated_improvement="Test",
                ),
            ],
        )

    def test_high_impact_opportunities(self, sample_stats: InstanceStatistics):
        """Test filtering high impact opportunities."""
        high = sample_stats.high_impact_opportunities
        assert len(high) == 1
        assert high[0].title == "High Impact"

    def test_medium_impact_opportunities(self, sample_stats: InstanceStatistics):
        """Test filtering medium impact opportunities."""
        medium = sample_stats.medium_impact_opportunities
        assert len(medium) == 1
        assert medium[0].title == "Medium Impact"

    def test_low_impact_opportunities(self, sample_stats: InstanceStatistics):
        """Test filtering low impact opportunities."""
        low = sample_stats.low_impact_opportunities
        assert len(low) == 1
        assert low[0].title == "Low Impact"

    def test_get_coverage_summary(self, sample_stats: InstanceStatistics):
        """Test coverage summary generation."""
        summary = sample_stats.get_coverage_summary()

        assert summary["searchable"] == "2/3"
        assert summary["filterable"] == "1/3"
        assert summary["sortable"] == "1/3"

    def test_get_coverage_summary_empty(self):
        """Test coverage summary with no indexes."""
        stats = InstanceStatistics(total_indexes=0)
        summary = stats.get_coverage_summary()

        assert summary == {}
