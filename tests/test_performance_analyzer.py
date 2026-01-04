"""Tests for the Performance Analyzer."""

import pytest

from meiliscan.analyzers.performance_analyzer import PerformanceAnalyzer
from meiliscan.models.finding import FindingCategory, FindingSeverity
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


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
            {"status": "succeeded", "type": "documentAdditionOrUpdate"}
            for _ in range(80)
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
            {"status": "succeeded", "type": "documentAdditionOrUpdate"}
            for _ in range(95)
        ] + [{"status": "failed", "type": "documentAdditionOrUpdate"} for _ in range(5)]

        findings = analyzer.analyze_global([], {}, tasks)
        p001_findings = [f for f in findings if f.id == "MEILI-P001"]
        assert len(p001_findings) == 0

    def test_no_p001_with_few_tasks(self, analyzer):
        """Test no P001 finding with <10 tasks."""
        tasks = [
            {"status": "succeeded", "type": "documentAdditionOrUpdate"}
            for _ in range(5)
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
        tasks = [{"status": "succeeded", "type": "settingsUpdate"} for _ in range(10)]

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
            {"status": "succeeded", "type": "documentAdditionOrUpdate"}
            for _ in range(70)
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

    # P007: Task backlog tests

    def test_task_backlog_detection_p007(self, analyzer):
        """Test detection of sustained task backlog (P007)."""
        # Tasks with high queue times (>60s average)
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "enqueuedAt": "2025-01-04T10:00:00Z",
                "startedAt": "2025-01-04T10:02:00Z",  # 2 minute wait
            }
            for _ in range(10)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p007_findings = [f for f in findings if f.id == "MEILI-P007"]

        assert len(p007_findings) == 1
        assert p007_findings[0].severity == FindingSeverity.WARNING
        assert "backlog" in p007_findings[0].title.lower()
        assert p007_findings[0].current_value["avg_queue_time_seconds"] == 120.0

    def test_no_p007_with_fast_queue(self, analyzer):
        """Test no P007 finding with fast queue processing."""
        # Tasks with low queue times (<60s average)
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "enqueuedAt": "2025-01-04T10:00:00Z",
                "startedAt": "2025-01-04T10:00:05Z",  # 5 second wait
            }
            for _ in range(10)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p007_findings = [f for f in findings if f.id == "MEILI-P007"]

        assert len(p007_findings) == 0

    def test_no_p007_with_few_tasks(self, analyzer):
        """Test no P007 finding with insufficient tasks."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "enqueuedAt": "2025-01-04T10:00:00Z",
                "startedAt": "2025-01-04T10:02:00Z",
            }
            for _ in range(3)  # Less than 5 timed tasks
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p007_findings = [f for f in findings if f.id == "MEILI-P007"]

        assert len(p007_findings) == 0

    def test_p007_handles_missing_timestamps(self, analyzer):
        """Test P007 gracefully handles tasks without timestamps."""
        tasks = [
            {"status": "succeeded", "type": "documentAdditionOrUpdate"}  # No timestamps
            for _ in range(10)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p007_findings = [f for f in findings if f.id == "MEILI-P007"]

        assert len(p007_findings) == 0  # No error, just no finding

    # P008: Tiny indexing tasks tests

    def test_tiny_indexing_tasks_detection_p008(self, analyzer):
        """Test detection of too many tiny indexing tasks (P008)."""
        # More than 50% tiny tasks
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"receivedDocuments": 2},  # Tiny: <10 docs
            }
            for _ in range(15)
        ] + [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"receivedDocuments": 100},  # Normal
            }
            for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p008_findings = [f for f in findings if f.id == "MEILI-P008"]

        assert len(p008_findings) == 1
        assert p008_findings[0].severity == FindingSeverity.SUGGESTION
        assert "tiny" in p008_findings[0].title.lower()
        assert p008_findings[0].current_value["tiny_tasks"] == 15

    def test_no_p008_with_normal_batch_sizes(self, analyzer):
        """Test no P008 finding with normal batch sizes."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"receivedDocuments": 100},
            }
            for _ in range(20)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p008_findings = [f for f in findings if f.id == "MEILI-P008"]

        assert len(p008_findings) == 0

    def test_no_p008_with_low_tiny_ratio(self, analyzer):
        """Test no P008 finding when tiny tasks ratio is below threshold."""
        # Only 30% tiny tasks (below 50% threshold)
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"receivedDocuments": 5},  # Tiny
            }
            for _ in range(6)
        ] + [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"receivedDocuments": 100},  # Normal
            }
            for _ in range(14)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p008_findings = [f for f in findings if f.id == "MEILI-P008"]

        assert len(p008_findings) == 0

    def test_no_p008_with_few_tasks(self, analyzer):
        """Test no P008 finding with insufficient tasks."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"receivedDocuments": 2},
            }
            for _ in range(10)  # Less than 20 doc tasks
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p008_findings = [f for f in findings if f.id == "MEILI-P008"]

        assert len(p008_findings) == 0

    def test_p008_uses_indexed_documents_fallback(self, analyzer):
        """Test P008 uses indexedDocuments when receivedDocuments is missing."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"indexedDocuments": 3},  # Tiny via fallback field
            }
            for _ in range(15)
        ] + [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "details": {"indexedDocuments": 500},
            }
            for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p008_findings = [f for f in findings if f.id == "MEILI-P008"]

        assert len(p008_findings) == 1

    # P009: Oversized indexing tasks tests

    def test_oversized_indexing_tasks_detection_p009(self, analyzer):
        """Test detection of oversized indexing tasks (P009)."""
        # Tasks with >10 minute duration
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": "PT720S",  # 12 minutes
                "details": {"receivedDocuments": 50000},
            },
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": "PT900S",  # 15 minutes
                "details": {"receivedDocuments": 100000},
            },
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p009_findings = [f for f in findings if f.id == "MEILI-P009"]

        assert len(p009_findings) == 1
        assert p009_findings[0].severity == FindingSeverity.SUGGESTION
        assert "oversized" in p009_findings[0].title.lower()
        assert p009_findings[0].current_value["slow_task_count"] == 2

    def test_p009_with_minutes_duration_format(self, analyzer):
        """Test P009 handles PT15M30S duration format."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": "PT15M30.5S",  # 15 minutes 30.5 seconds
                "details": {"receivedDocuments": 50000},
            }
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p009_findings = [f for f in findings if f.id == "MEILI-P009"]

        assert len(p009_findings) == 1
        # 15*60 + 30.5 = 930.5 seconds = 15.5 minutes
        assert p009_findings[0].current_value["avg_duration_minutes"] == 15.5

    def test_p009_with_numeric_duration(self, analyzer):
        """Test P009 handles numeric duration values."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": 700,  # 700 seconds = 11.7 minutes
                "details": {"receivedDocuments": 50000},
            }
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p009_findings = [f for f in findings if f.id == "MEILI-P009"]

        assert len(p009_findings) == 1

    def test_no_p009_with_fast_tasks(self, analyzer):
        """Test no P009 finding with fast tasks."""
        tasks = [
            {
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "duration": "PT60S",  # 1 minute
                "details": {"receivedDocuments": 1000},
            }
            for _ in range(10)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p009_findings = [f for f in findings if f.id == "MEILI-P009"]

        assert len(p009_findings) == 0

    # P010: Error clustering tests

    def test_error_clustering_detection_p010(self, analyzer):
        """Test detection of recurring task failures (P010)."""
        tasks = [
            {
                "status": "failed",
                "type": "documentAdditionOrUpdate",
                "error": {
                    "code": "invalid_document_id",
                    "message": "Document id must be an integer or a string",
                    "type": "invalid_request",
                },
            }
            for _ in range(5)  # 5 same errors
        ] + [
            {
                "status": "failed",
                "type": "documentAdditionOrUpdate",
                "error": {
                    "code": "missing_document_id",
                    "message": "Document doesn't have a primary key",
                    "type": "invalid_request",
                },
            }
            for _ in range(3)  # 3 different errors
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p010_findings = [f for f in findings if f.id == "MEILI-P010"]

        assert len(p010_findings) == 1
        assert p010_findings[0].severity == FindingSeverity.WARNING
        assert "recurring" in p010_findings[0].title.lower()

        # Should report both error codes that have >= 3 occurrences
        recurring_errors = p010_findings[0].current_value["recurring_errors"]
        error_codes = {e["code"] for e in recurring_errors}
        assert "invalid_document_id" in error_codes
        assert "missing_document_id" in error_codes

    def test_no_p010_with_unique_errors(self, analyzer):
        """Test no P010 finding when errors are unique."""
        tasks = [
            {
                "status": "failed",
                "type": "documentAdditionOrUpdate",
                "error": {
                    "code": f"error_{i}",
                    "message": f"Unique error {i}",
                },
            }
            for i in range(10)  # 10 different errors, none repeating
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p010_findings = [f for f in findings if f.id == "MEILI-P010"]

        assert len(p010_findings) == 0

    def test_no_p010_with_few_failures(self, analyzer):
        """Test no P010 finding with insufficient failed tasks."""
        tasks = [
            {
                "status": "failed",
                "type": "documentAdditionOrUpdate",
                "error": {"code": "same_error", "message": "Same error"},
            }
            for _ in range(2)  # Less than 3 failed tasks
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p010_findings = [f for f in findings if f.id == "MEILI-P010"]

        assert len(p010_findings) == 0

    def test_p010_handles_missing_error_details(self, analyzer):
        """Test P010 gracefully handles tasks without error details."""
        tasks = [
            {"status": "failed", "type": "documentAdditionOrUpdate"}  # No error field
            for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p010_findings = [f for f in findings if f.id == "MEILI-P010"]

        # Should not crash, and no finding since no error info
        assert len(p010_findings) == 0

    def test_p010_truncates_long_messages(self, analyzer):
        """Test P010 truncates long error messages in output."""
        long_message = "A" * 500  # Very long message
        tasks = [
            {
                "status": "failed",
                "type": "documentAdditionOrUpdate",
                "error": {"code": "test_error", "message": long_message},
            }
            for _ in range(5)
        ]

        findings = analyzer.analyze_global([], {}, tasks)
        p010_findings = [f for f in findings if f.id == "MEILI-P010"]

        assert len(p010_findings) == 1
        # Message should be truncated
        error_msg = p010_findings[0].current_value["recurring_errors"][0]["message"]
        assert len(error_msg) <= 100
