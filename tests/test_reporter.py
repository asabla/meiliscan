"""Tests for Reporter parallel analysis functionality."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meiliscan.core.analyzer import Analyzer
from meiliscan.core.collector import DataCollector
from meiliscan.core.reporter import Reporter
from meiliscan.models.finding import Finding, FindingCategory, FindingSeverity
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


class TestReporterParallelAnalysis:
    """Tests for parallel index analysis in Reporter."""

    @pytest.fixture
    def mock_collector(self) -> MagicMock:
        """Create a mock DataCollector with multiple indexes."""
        collector = MagicMock(spec=DataCollector)
        collector.version = "1.6.0"
        collector.global_stats = {"databaseSize": 1024}
        collector.tasks = []
        collector.indexes = [
            IndexData(
                uid=f"index-{i}",
                settings=IndexSettings(),
                stats=IndexStats(numberOfDocuments=100),
                sample_documents=[{"id": j} for j in range(5)],
            )
            for i in range(10)
        ]
        return collector

    @pytest.fixture
    def mock_finding(self) -> Finding:
        """Create a mock finding."""
        return Finding(
            id="MEILI-TEST",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.WARNING,
            title="Test finding",
            description="Test description",
            impact="Test impact",
        )

    @pytest.mark.asyncio
    async def test_generate_report_returns_analysis_report(self, mock_collector):
        """Test that generate_report returns an AnalysisReport."""
        reporter = Reporter(mock_collector)
        report = await reporter.generate_report()

        assert report is not None
        assert report.source.meilisearch_version == "1.6.0"
        assert len(report.indexes) == 10

    @pytest.mark.asyncio
    async def test_generate_report_with_progress_callback(self, mock_collector):
        """Test that progress callback is called during report generation."""
        reporter = Reporter(mock_collector)
        progress_events = []

        async def progress_cb(event):
            progress_events.append(event)

        report = await reporter.generate_report(progress_cb=progress_cb)

        assert report is not None
        # Should have progress events for analyzing indexes
        assert len(progress_events) > 0
        # Check that we have events for index analysis
        index_events = [e for e in progress_events if e.index_uid]
        assert len(index_events) > 0

    @pytest.mark.asyncio
    async def test_parallel_analysis_respects_max_concurrent(self, mock_collector):
        """Test that parallel analysis respects max_concurrent limit."""
        max_concurrent = 2
        concurrent_count = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def tracking_analyze(self, index, detect_sensitive=False):
            nonlocal concurrent_count, max_seen
            async with lock:
                concurrent_count += 1
                if concurrent_count > max_seen:
                    max_seen = concurrent_count

            try:
                await asyncio.sleep(0.05)  # Simulate work
                return []  # Return empty findings
            finally:
                async with lock:
                    concurrent_count -= 1

        with patch.object(Analyzer, "analyze_index", tracking_analyze):
            reporter = Reporter(mock_collector, max_concurrent=max_concurrent)
            await reporter.generate_report()

        # Should never exceed max_concurrent
        assert max_seen <= max_concurrent

    @pytest.mark.asyncio
    async def test_parallel_analysis_faster_than_serial(self, mock_collector):
        """Test that parallel analysis is faster than serial execution."""

        # Create analyzer that takes some time
        async def slow_analyze(self, index, detect_sensitive=False):
            await asyncio.sleep(0.02)
            return []

        with patch.object(Analyzer, "analyze_index", slow_analyze):
            # Serial execution (max_concurrent=1)
            reporter_serial = Reporter(mock_collector, max_concurrent=1)
            start_serial = asyncio.get_event_loop().time()
            await reporter_serial.generate_report()
            serial_time = asyncio.get_event_loop().time() - start_serial

            # Parallel execution (max_concurrent=10)
            reporter_parallel = Reporter(mock_collector, max_concurrent=10)
            start_parallel = asyncio.get_event_loop().time()
            await reporter_parallel.generate_report()
            parallel_time = asyncio.get_event_loop().time() - start_parallel

        # Parallel should be significantly faster (at least 2x for 10 indexes)
        assert parallel_time < serial_time * 0.8

    @pytest.mark.asyncio
    async def test_findings_aggregated_correctly(self, mock_collector, mock_finding):
        """Test that findings from all indexes are aggregated correctly."""

        # Create analyzer that returns one finding per index
        async def analyze_with_finding(self, index, detect_sensitive=False):
            return [
                Finding(
                    id=f"MEILI-{index.uid}",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title=f"Finding for {index.uid}",
                    description="Test",
                    impact="Test",
                    index_uid=index.uid,
                )
            ]

        with patch.object(Analyzer, "analyze_index", analyze_with_finding):
            # Also mock global analysis to return empty
            with patch.object(Analyzer, "analyze_global", AsyncMock(return_value=[])):
                reporter = Reporter(mock_collector)
                report = await reporter.generate_report()

        # Should have one finding per index
        all_findings = report.get_all_findings()
        assert len(all_findings) == 10

        # Each finding should have the correct index_uid
        index_uids = {f.index_uid for f in all_findings}
        expected_uids = {f"index-{i}" for i in range(10)}
        assert index_uids == expected_uids

    @pytest.mark.asyncio
    async def test_action_plan_generated(self, mock_collector, mock_finding):
        """Test that action plan is generated from findings."""

        async def analyze_with_findings(self, index, detect_sensitive=False):
            return [
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Critical issue",
                    description="Test",
                    impact="Test",
                    index_uid=index.uid,
                ),
                Finding(
                    id="MEILI-S002",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title="Warning issue",
                    description="Test",
                    impact="Test",
                    index_uid=index.uid,
                ),
            ]

        with patch.object(Analyzer, "analyze_index", analyze_with_findings):
            with patch.object(Analyzer, "analyze_global", AsyncMock(return_value=[])):
                reporter = Reporter(mock_collector)
                report = await reporter.generate_report()

        # Action plan should be generated
        assert report.action_plan is not None
        assert len(report.action_plan.priority_order) > 0
        # Critical issues should come first
        assert "MEILI-S001" in report.action_plan.priority_order

    @pytest.mark.asyncio
    async def test_empty_indexes_handled(self):
        """Test that empty index list is handled correctly."""
        collector = MagicMock(spec=DataCollector)
        collector.version = "1.6.0"
        collector.global_stats = {}
        collector.tasks = []
        collector.indexes = []

        reporter = Reporter(collector)
        report = await reporter.generate_report()

        assert report is not None
        assert len(report.indexes) == 0

    @pytest.mark.asyncio
    async def test_probe_findings_included(self, mock_collector, mock_finding):
        """Test that probe findings are included in report."""
        probe_finding = Finding(
            id="MEILI-P001",
            category=FindingCategory.PERFORMANCE,
            severity=FindingSeverity.WARNING,
            title="Search probe finding",
            description="From search probe",
            impact="Test",
        )

        analysis_options = {"_probe_findings": [probe_finding]}

        with patch.object(Analyzer, "analyze_index", AsyncMock(return_value=[])):
            with patch.object(Analyzer, "analyze_global", AsyncMock(return_value=[])):
                reporter = Reporter(mock_collector, analysis_options=analysis_options)
                report = await reporter.generate_report()

        # Probe finding should be in the report
        all_findings = report.get_all_findings()
        assert any(f.id == "MEILI-P001" for f in all_findings)


class TestAnalyzerParallelExecution:
    """Tests for parallel analyzer execution within Analyzer."""

    @pytest.fixture
    def sample_index(self) -> IndexData:
        """Create a sample index for testing."""
        return IndexData(
            uid="test-index",
            settings=IndexSettings(searchableAttributes=["*"]),
            stats=IndexStats(numberOfDocuments=100),
            sample_documents=[{"id": i, "title": f"Doc {i}"} for i in range(10)],
        )

    @pytest.mark.asyncio
    async def test_analyze_index_is_async(self, sample_index):
        """Test that analyze_index is an async method."""
        analyzer = Analyzer()
        result = analyzer.analyze_index(sample_index)

        # Should return a coroutine
        assert asyncio.iscoroutine(result)

        # Execute and verify
        findings = await result
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_analyze_all_is_async(self, sample_index):
        """Test that analyze_all is an async method."""
        analyzer = Analyzer()
        result = analyzer.analyze_all([sample_index])

        # Should return a coroutine
        assert asyncio.iscoroutine(result)

        # Execute and verify - returns dict[index_uid, list[Finding]]
        findings_by_index = await result
        assert isinstance(findings_by_index, dict)
        assert sample_index.uid in findings_by_index

    @pytest.mark.asyncio
    async def test_analyze_global_is_async(self, sample_index):
        """Test that analyze_global is an async method."""
        analyzer = Analyzer()
        result = analyzer.analyze_global(indexes=[sample_index], global_stats={})

        # Should return a coroutine
        assert asyncio.iscoroutine(result)

        # Execute and verify
        findings = await result
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_multiple_indexes_analyzed_concurrently(self, sample_index):
        """Test that multiple indexes can be analyzed concurrently."""
        indexes = [
            IndexData(
                uid=f"test-{i}",
                settings=IndexSettings(),
                stats=IndexStats(numberOfDocuments=10),
                sample_documents=[{"id": 1}],
            )
            for i in range(5)
        ]

        analyzer = Analyzer()

        # Create tasks for concurrent analysis
        tasks = [analyzer.analyze_index(idx) for idx in indexes]

        # Run concurrently
        results = await asyncio.gather(*tasks)

        # Should have results for each index
        assert len(results) == 5
        for result in results:
            assert isinstance(result, list)
