"""Tests for the Performance Analyzer."""

import pytest

from meilisearch_analyzer.analyzers.performance_analyzer import PerformanceAnalyzer
from meilisearch_analyzer.models.finding import FindingCategory, FindingSeverity
from meilisearch_analyzer.models.index import IndexData, IndexSettings, IndexStats


class TestPerformanceAnalyzer:
    """Tests for PerformanceAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> PerformanceAnalyzer:
        """Create a performance analyzer instance."""
        return PerformanceAnalyzer()

    @pytest.fixture
    def basic_index(self) -> IndexData:
        """Create a basic index for testing."""
        return IndexData(
            uid="test_index",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=1000,
                fieldDistribution={
                    "id": 1000,
                    "title": 1000,
                    "description": 1000,
                },
            ),
        )

    def test_analyzer_name(self, analyzer):
        """Test analyzer name property."""
        assert analyzer.name == "performance"

    # Per-index tests

    def test_too_many_fields_detection_p006(self, analyzer):
        """Test detection of too many unique fields (P006)."""
        # Create index with >100 fields
        fields = {f"field_{i}": 1000 for i in range(120)}
        index = IndexData(
            uid="test",
            stats=IndexStats(numberOfDocuments=1000, fieldDistribution=fields),
        )

        findings = analyzer.analyze(index)
        p006_findings = [f for f in findings if f.id == "MEILI-P006"]
        assert len(p006_findings) == 1
        assert p006_findings[0].severity == FindingSeverity.WARNING
        assert p006_findings[0].category == FindingCategory.PERFORMANCE
        assert p006_findings[0].current_value == 120

    def test_no_p006_with_few_fields(self, analyzer, basic_index):
        """Test no P006 finding with few fields."""
        findings = analyzer.analyze(basic_index)
        p006_findings = [f for f in findings if f.id == "MEILI-P006"]
        assert len(p006_findings) == 0

    # Global tests - task failures

    def test_high_task_failure_rate_p001(self, analyzer):
        """Test detection of high task failure rate (P001)."""
        # Create tasks with >10% failure rate
        tasks = [
            {"status": "succeeded", "type": "documentAdditionOrUpdate"} for _ in range(80)
        ] + [
            {"status": "failed", "type": "documentAdditionOrUpdate"} for _ in range(20)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p001_findings = [f for f in findings if f.id == "MEILI-P001"]
        assert len(p001_findings) == 1
        assert p001_findings[0].severity == FindingSeverity.CRITICAL
        assert "20.0%" in p001_findings[0].current_value

    def test_no_p001_with_low_failure_rate(self, analyzer):
        """Test no P001 finding with low failure rate."""
        tasks = [
            {"status": "succeeded", "type": "documentAdditionOrUpdate"} for _ in range(95)
        ] + [
            {"status": "failed", "type": "documentAdditionOrUpdate"} for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p001_findings = [f for f in findings if f.id == "MEILI-P001"]
        assert len(p001_findings) == 0

    def test_no_p001_with_few_tasks(self, analyzer):
        """Test no P001 finding with <10 tasks."""
        tasks = [
            {"status": "succeeded", "type": "documentAdditionOrUpdate"} for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p001_findings = [f for f in findings if f.id == "MEILI-P001"]
        assert len(p001_findings) == 0

    def test_no_p001_without_tasks(self, analyzer):
        """Test no P001 finding without tasks."""
        findings = analyzer.analyze_global([], {}, None)
        p001_findings = [f for f in findings if f.id == "MEILI-P001"]
        assert len(p001_findings) == 0

    # Global tests - slow indexing

    def test_slow_indexing_detection_p002(self, analyzer):
        """Test detection of slow indexing (P002)."""
        # Tasks with >5 minute average duration
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": "PT400S",  # 400 seconds
            }
            for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p002_findings = [f for f in findings if f.id == "MEILI-P002"]
        assert len(p002_findings) == 1
        assert p002_findings[0].severity == FindingSeverity.WARNING

    def test_slow_indexing_with_numeric_duration(self, analyzer):
        """Test P002 with numeric duration values."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": 350,  # numeric seconds
            }
            for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p002_findings = [f for f in findings if f.id == "MEILI-P002"]
        assert len(p002_findings) == 1

    def test_no_p002_with_fast_indexing(self, analyzer):
        """Test no P002 finding with fast indexing."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": "PT10S",  # 10 seconds
            }
            for _ in range(10)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p002_findings = [f for f in findings if f.id == "MEILI-P002"]
        assert len(p002_findings) == 0

    def test_no_p002_without_indexing_tasks(self, analyzer):
        """Test no P002 finding without indexing tasks."""
        tasks = [
            {"status": "succeeded", "type": "settingsUpdate"}
            for _ in range(10)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p002_findings = [f for f in findings if f.id == "MEILI-P002"]
        assert len(p002_findings) == 0

    # Global tests - database fragmentation

    def test_database_fragmentation_p003(self, analyzer):
        """Test detection of database fragmentation (P003)."""
        global_stats = {
            "databaseSize": 1000000,  # 1MB total
            "usedDatabaseSize": 400000,  # 400KB used = 40% utilization
        }

        findings = analyzer.analyze_global([], global_stats, None)
        p003_findings = [f for f in findings if f.id == "MEILI-P003"]
        assert len(p003_findings) == 1
        assert p003_findings[0].severity == FindingSeverity.SUGGESTION
        assert "40%" in p003_findings[0].current_value["utilization"]

    def test_no_p003_with_good_utilization(self, analyzer):
        """Test no P003 finding with good utilization."""
        global_stats = {
            "databaseSize": 1000000,
            "usedDatabaseSize": 800000,  # 80% utilization
        }

        findings = analyzer.analyze_global([], global_stats, None)
        p003_findings = [f for f in findings if f.id == "MEILI-P003"]
        assert len(p003_findings) == 0

    def test_no_p003_without_stats(self, analyzer):
        """Test no P003 finding without stats."""
        findings = analyzer.analyze_global([], {}, None)
        p003_findings = [f for f in findings if f.id == "MEILI-P003"]
        assert len(p003_findings) == 0

    # Global tests - index count

    def test_too_many_indexes_p004(self, analyzer):
        """Test detection of too many indexes (P004)."""
        indexes = [IndexData(uid=f"index_{i}") for i in range(25)]

        findings = analyzer.analyze_global(indexes, {}, None)
        p004_findings = [f for f in findings if f.id == "MEILI-P004"]
        assert len(p004_findings) == 1
        assert p004_findings[0].severity == FindingSeverity.SUGGESTION
        assert p004_findings[0].current_value == 25

    def test_no_p004_with_few_indexes(self, analyzer):
        """Test no P004 finding with few indexes."""
        indexes = [IndexData(uid=f"index_{i}") for i in range(5)]

        findings = analyzer.analyze_global(indexes, {}, None)
        p004_findings = [f for f in findings if f.id == "MEILI-P004"]
        assert len(p004_findings) == 0

    # Global tests - index imbalance

    def test_index_imbalance_p005(self, analyzer):
        """Test detection of index imbalance (P005)."""
        indexes = [
            IndexData(
                uid="dominant",
                stats=IndexStats(numberOfDocuments=9000),
            ),
            IndexData(
                uid="small1",
                stats=IndexStats(numberOfDocuments=500),
            ),
            IndexData(
                uid="small2",
                stats=IndexStats(numberOfDocuments=500),
            ),
        ]

        findings = analyzer.analyze_global(indexes, {}, None)
        p005_findings = [f for f in findings if f.id == "MEILI-P005"]
        assert len(p005_findings) == 1
        assert p005_findings[0].severity == FindingSeverity.INFO
        assert "dominant" in p005_findings[0].current_value["dominant_index"]

    def test_no_p005_with_balanced_indexes(self, analyzer):
        """Test no P005 finding with balanced indexes."""
        indexes = [
            IndexData(
                uid=f"index_{i}",
                stats=IndexStats(numberOfDocuments=1000),
            )
            for i in range(5)
        ]

        findings = analyzer.analyze_global(indexes, {}, None)
        p005_findings = [f for f in findings if f.id == "MEILI-P005"]
        assert len(p005_findings) == 0

    def test_no_p005_with_single_index(self, analyzer, basic_index):
        """Test no P005 finding with single index."""
        findings = analyzer.analyze_global([basic_index], {}, None)
        p005_findings = [f for f in findings if f.id == "MEILI-P005"]
        assert len(p005_findings) == 0

    def test_no_p005_with_empty_indexes(self, analyzer):
        """Test no P005 finding with empty indexes."""
        indexes = [
            IndexData(uid=f"index_{i}", stats=IndexStats(numberOfDocuments=0))
            for i in range(3)
        ]

        findings = analyzer.analyze_global(indexes, {}, None)
        p005_findings = [f for f in findings if f.id == "MEILI-P005"]
        assert len(p005_findings) == 0

    # Combined tests

    def test_multiple_global_findings(self, analyzer):
        """Test multiple global findings at once."""
        # Create scenario with multiple issues
        indexes = [IndexData(uid=f"index_{i}") for i in range(25)]  # P004
        global_stats = {
            "databaseSize": 1000000,
            "usedDatabaseSize": 400000,  # P003
        }
        tasks = [
            {"status": "failed", "type": "documentAdditionOrUpdate"} for _ in range(30)
        ] + [
            {"status": "succeeded", "type": "documentAdditionOrUpdate"} for _ in range(70)
        ]  # P001

        findings = analyzer.analyze_global(indexes, global_stats, tasks)

        finding_ids = {f.id for f in findings}
        assert "MEILI-P001" in finding_ids
        assert "MEILI-P003" in finding_ids
        assert "MEILI-P004" in finding_ids

    def test_per_index_analyze_returns_list(self, analyzer, basic_index):
        """Test that per-index analyze always returns a list."""
        findings = analyzer.analyze(basic_index)
        assert isinstance(findings, list)

    def test_global_analyze_returns_list(self, analyzer):
        """Test that global analyze always returns a list."""
        findings = analyzer.analyze_global([], {}, None)
        assert isinstance(findings, list)
