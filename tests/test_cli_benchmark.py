"""Tests for the benchmark CLI command."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from meiliscan.cli import app
from meiliscan.models.benchmark import (
    BenchmarkReport,
    IndexBenchmark,
    SearchBenchmarkResult,
    SearchQuery,
)
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_index() -> IndexData:
    """Create a sample index for testing."""
    return IndexData(
        uid="test-index",
        primary_key="id",
        settings=IndexSettings(
            searchable_attributes=["title", "description"],
            filterable_attributes=["category"],
            sortable_attributes=["created_at"],
        ),
        stats=IndexStats(number_of_documents=1000),
    )


@pytest.fixture
def sample_benchmark_report() -> BenchmarkReport:
    """Create a sample benchmark report for testing."""
    query = SearchQuery(query_type="baseline", query_text="")
    result = SearchBenchmarkResult(
        index_uid="test-index",
        query=query,
        latency_ms=10.5,
        processing_time_ms=5.2,
        hits_count=100,
        response_size_bytes=4096,
        success=True,
    )

    index_benchmark = IndexBenchmark(
        index_uid="test-index",
        document_count=1000,
        baseline_latency_ms=10.5,
        text_latency_ms=15.3,
        filtered_latency_ms=12.1,
        sorted_latency_ms=11.8,
        queries=[result],
    )

    return BenchmarkReport(
        ran_at=datetime(2024, 1, 1, 12, 0, 0),
        source_url="http://localhost:7700",
        source_type="instance",
        duration_ms=500.0,
        total_queries=6,
        avg_baseline_ms=10.5,
        avg_overall_ms=12.4,
        p50_latency_ms=11.0,
        p95_latency_ms=15.0,
        p99_latency_ms=18.0,
        min_latency_ms=8.0,
        max_latency_ms=20.0,
        indexes=[index_benchmark],
        slowest_queries=[result],
        fastest_queries=[result],
        comprehensive=False,
        queries_per_type=1,
    )


class TestBenchmarkCommand:
    """Tests for the benchmark CLI command."""

    def test_benchmark_requires_url(self, runner: CliRunner):
        """Test that benchmark command requires URL option."""
        result = runner.invoke(app, ["benchmark"])
        assert result.exit_code != 0
        # Exit code 2 indicates missing required option

    def test_benchmark_invalid_format(self, runner: CliRunner):
        """Test that benchmark command rejects invalid format."""
        result = runner.invoke(
            app,
            ["benchmark", "--url", "http://localhost:7700", "--format", "invalid"],
        )
        assert result.exit_code == 1
        assert "Unknown format" in result.stdout

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_accepts_url(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command accepts URL option."""
        mock_run.return_value = 0

        result = runner.invoke(app, ["benchmark", "--url", "http://localhost:7700"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == "http://localhost:7700"

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_accepts_api_key(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command accepts API key option."""
        mock_run.return_value = 0

        result = runner.invoke(
            app,
            ["benchmark", "-u", "http://localhost:7700", "-k", "test-key"],
        )

        assert result.exit_code == 0
        call_args = mock_run.call_args
        assert call_args[0][1] == "test-key"

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_comprehensive_flag(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command accepts comprehensive flag."""
        mock_run.return_value = 0

        result = runner.invoke(
            app,
            ["benchmark", "-u", "http://localhost:7700", "--comprehensive"],
        )

        assert result.exit_code == 0
        call_args = mock_run.call_args
        assert call_args[0][2] is True  # comprehensive flag

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_output_option(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command accepts output option."""
        mock_run.return_value = 0

        result = runner.invoke(
            app,
            ["benchmark", "-u", "http://localhost:7700", "-o", "results.json"],
        )

        assert result.exit_code == 0
        call_args = mock_run.call_args
        assert call_args[0][3] == Path("results.json")

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_format_option(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command accepts format option."""
        mock_run.return_value = 0

        result = runner.invoke(
            app,
            ["benchmark", "-u", "http://localhost:7700", "-f", "markdown"],
        )

        assert result.exit_code == 0
        call_args = mock_run.call_args
        assert call_args[0][4] == "markdown"

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_indexes_option(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command accepts indexes filter option."""
        mock_run.return_value = 0

        result = runner.invoke(
            app,
            [
                "benchmark",
                "-u",
                "http://localhost:7700",
                "--indexes",
                "products,articles",
            ],
        )

        assert result.exit_code == 0
        call_args = mock_run.call_args
        assert call_args[0][5] == ["products", "articles"]

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_indexes_with_spaces(
        self, mock_run: MagicMock, runner: CliRunner
    ):
        """Test that benchmark command handles spaces in indexes list."""
        mock_run.return_value = 0

        result = runner.invoke(
            app,
            [
                "benchmark",
                "-u",
                "http://localhost:7700",
                "-i",
                "products, articles, users",
            ],
        )

        assert result.exit_code == 0
        call_args = mock_run.call_args
        # Should strip whitespace
        assert call_args[0][5] == ["products", "articles", "users"]

    @patch("meiliscan.cli._run_benchmark")
    def test_benchmark_returns_error_code(self, mock_run: MagicMock, runner: CliRunner):
        """Test that benchmark command returns non-zero exit code on failure."""
        mock_run.return_value = 1

        result = runner.invoke(app, ["benchmark", "-u", "http://localhost:7700"])

        assert result.exit_code == 1


class TestRunBenchmark:
    """Tests for the _run_benchmark async function."""

    @pytest.fixture
    def mock_collector(self, sample_index: IndexData):
        """Create a mock LiveInstanceCollector."""
        collector = MagicMock()
        collector.connect = AsyncMock(return_value=True)
        collector.close = AsyncMock()
        collector.get_indexes = AsyncMock(return_value=[sample_index])
        collector.url = "http://localhost:7700"
        return collector

    @pytest.fixture
    def mock_runner(self, sample_benchmark_report: BenchmarkReport):
        """Create a mock SearchBenchmarkRunner."""
        runner = MagicMock()
        runner.run_baseline = AsyncMock(return_value=sample_benchmark_report)
        runner.run_comprehensive = AsyncMock(return_value=sample_benchmark_report)
        return runner

    @pytest.mark.asyncio
    async def test_run_benchmark_connects_to_instance(
        self, mock_collector: MagicMock, mock_runner: MagicMock
    ):
        """Test that _run_benchmark connects to the MeiliSearch instance."""
        with (
            patch(
                "meiliscan.collectors.live_instance.LiveInstanceCollector",
                return_value=mock_collector,
            ),
            patch(
                "meiliscan.benchmarks.search_runner.SearchBenchmarkRunner",
                return_value=mock_runner,
            ),
        ):
            from meiliscan.cli import _run_benchmark

            exit_code = await _run_benchmark(
                url="http://localhost:7700",
                api_key=None,
                comprehensive=False,
                output=None,
                format_type="json",
                index_filter=None,
            )

            assert exit_code == 0
            mock_collector.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_benchmark_fails_on_connection_error(
        self, mock_collector: MagicMock
    ):
        """Test that _run_benchmark returns error on connection failure."""
        mock_collector.connect = AsyncMock(return_value=False)

        with patch(
            "meiliscan.collectors.live_instance.LiveInstanceCollector",
            return_value=mock_collector,
        ):
            from meiliscan.cli import _run_benchmark

            exit_code = await _run_benchmark(
                url="http://localhost:7700",
                api_key=None,
                comprehensive=False,
                output=None,
                format_type="json",
                index_filter=None,
            )

            assert exit_code == 1

    @pytest.mark.asyncio
    async def test_run_benchmark_fails_on_no_indexes(self, mock_collector: MagicMock):
        """Test that _run_benchmark returns error when no indexes found."""
        mock_collector.get_indexes = AsyncMock(return_value=[])

        with patch(
            "meiliscan.collectors.live_instance.LiveInstanceCollector",
            return_value=mock_collector,
        ):
            from meiliscan.cli import _run_benchmark

            exit_code = await _run_benchmark(
                url="http://localhost:7700",
                api_key=None,
                comprehensive=False,
                output=None,
                format_type="json",
                index_filter=None,
            )

            assert exit_code == 1

    @pytest.mark.asyncio
    async def test_run_benchmark_filters_indexes(
        self,
        mock_collector: MagicMock,
        mock_runner: MagicMock,
        sample_index: IndexData,
    ):
        """Test that _run_benchmark filters indexes by UID."""
        other_index = IndexData(
            uid="other-index",
            primary_key="id",
            settings=IndexSettings(),
            stats=IndexStats(number_of_documents=500),
        )
        mock_collector.get_indexes = AsyncMock(return_value=[sample_index, other_index])

        with (
            patch(
                "meiliscan.collectors.live_instance.LiveInstanceCollector",
                return_value=mock_collector,
            ),
            patch(
                "meiliscan.benchmarks.search_runner.SearchBenchmarkRunner",
                return_value=mock_runner,
            ),
        ):
            from meiliscan.cli import _run_benchmark

            exit_code = await _run_benchmark(
                url="http://localhost:7700",
                api_key=None,
                comprehensive=False,
                output=None,
                format_type="json",
                index_filter=["test-index"],
            )

            assert exit_code == 0
            # Should only benchmark filtered indexes
            mock_runner.run_baseline.assert_called_once()
            call_args = mock_runner.run_baseline.call_args
            indexes = call_args[0][0]
            assert len(indexes) == 1
            assert indexes[0].uid == "test-index"

    @pytest.mark.asyncio
    async def test_run_benchmark_fails_when_filter_matches_nothing(
        self, mock_collector: MagicMock, sample_index: IndexData
    ):
        """Test that _run_benchmark fails when filter matches no indexes."""
        mock_collector.get_indexes = AsyncMock(return_value=[sample_index])

        with patch(
            "meiliscan.collectors.live_instance.LiveInstanceCollector",
            return_value=mock_collector,
        ):
            from meiliscan.cli import _run_benchmark

            exit_code = await _run_benchmark(
                url="http://localhost:7700",
                api_key=None,
                comprehensive=False,
                output=None,
                format_type="json",
                index_filter=["nonexistent"],
            )

            assert exit_code == 1

    @pytest.mark.asyncio
    async def test_run_benchmark_runs_comprehensive(
        self, mock_collector: MagicMock, mock_runner: MagicMock
    ):
        """Test that _run_benchmark runs comprehensive mode when requested."""
        with (
            patch(
                "meiliscan.collectors.live_instance.LiveInstanceCollector",
                return_value=mock_collector,
            ),
            patch(
                "meiliscan.benchmarks.search_runner.SearchBenchmarkRunner",
                return_value=mock_runner,
            ),
        ):
            from meiliscan.cli import _run_benchmark

            exit_code = await _run_benchmark(
                url="http://localhost:7700",
                api_key=None,
                comprehensive=True,
                output=None,
                format_type="json",
                index_filter=None,
            )

            assert exit_code == 0
            mock_runner.run_comprehensive.assert_called_once()
            mock_runner.run_baseline.assert_not_called()


class TestDisplayBenchmarkSummary:
    """Tests for the _display_benchmark_summary function."""

    def test_display_shows_latency_stats(
        self, sample_benchmark_report: BenchmarkReport, capsys
    ):
        """Test that display shows latency statistics."""
        from meiliscan.cli import _display_benchmark_summary

        _display_benchmark_summary(sample_benchmark_report)

        captured = capsys.readouterr()
        assert "10.50ms" in captured.out or "10.5ms" in captured.out  # avg baseline
        assert "12.40ms" in captured.out or "12.4ms" in captured.out  # avg overall
        assert "P50" in captured.out
        assert "P95" in captured.out
        assert "P99" in captured.out

    def test_display_shows_per_index_results(
        self, sample_benchmark_report: BenchmarkReport, capsys
    ):
        """Test that display shows per-index results table."""
        from meiliscan.cli import _display_benchmark_summary

        _display_benchmark_summary(sample_benchmark_report)

        captured = capsys.readouterr()
        assert "test-index" in captured.out
        assert "1,000" in captured.out  # document count

    def test_display_shows_slowest_queries(
        self, sample_benchmark_report: BenchmarkReport, capsys
    ):
        """Test that display shows slowest queries."""
        from meiliscan.cli import _display_benchmark_summary

        _display_benchmark_summary(sample_benchmark_report)

        captured = capsys.readouterr()
        assert "Slowest Queries" in captured.out


class TestExportBenchmark:
    """Tests for the _export_benchmark function."""

    def test_export_json_format(
        self, sample_benchmark_report: BenchmarkReport, tmp_path: Path
    ):
        """Test that export creates valid JSON file."""
        from meiliscan.cli import _export_benchmark

        output_file = tmp_path / "benchmark.json"
        _export_benchmark(sample_benchmark_report, output_file, "json")

        assert output_file.exists()
        content = output_file.read_text()
        assert '"source_url"' in content
        assert '"avg_baseline_ms"' in content
        assert "http://localhost:7700" in content

    def test_export_markdown_format(
        self, sample_benchmark_report: BenchmarkReport, tmp_path: Path
    ):
        """Test that export creates valid Markdown file."""
        from meiliscan.cli import _export_benchmark

        output_file = tmp_path / "benchmark.md"
        _export_benchmark(sample_benchmark_report, output_file, "markdown")

        assert output_file.exists()
        content = output_file.read_text()
        assert "# MeiliSearch Benchmark Report" in content
        assert "## Summary" in content
        assert "Avg Baseline" in content
        assert "test-index" in content

    def test_export_no_output_no_file_created(
        self, sample_benchmark_report: BenchmarkReport, capsys
    ):
        """Test that no file is created when output is None."""
        from meiliscan.cli import _export_benchmark

        _export_benchmark(sample_benchmark_report, None, "json")

        captured = capsys.readouterr()
        assert "--output" in captured.out

    def test_export_json_contains_all_fields(
        self, sample_benchmark_report: BenchmarkReport, tmp_path: Path
    ):
        """Test that JSON export contains all expected fields."""
        import json

        from meiliscan.cli import _export_benchmark

        output_file = tmp_path / "benchmark.json"
        _export_benchmark(sample_benchmark_report, output_file, "json")

        data = json.loads(output_file.read_text())

        assert "ran_at" in data
        assert "source_url" in data
        assert "duration_ms" in data
        assert "total_queries" in data
        assert "avg_baseline_ms" in data
        assert "avg_overall_ms" in data
        assert "p50_latency_ms" in data
        assert "p95_latency_ms" in data
        assert "p99_latency_ms" in data
        assert "indexes" in data
        assert len(data["indexes"]) == 1
        assert data["indexes"][0]["index_uid"] == "test-index"

    def test_export_markdown_contains_per_index_section(
        self, sample_benchmark_report: BenchmarkReport, tmp_path: Path
    ):
        """Test that Markdown export contains per-index results."""
        from meiliscan.cli import _export_benchmark

        output_file = tmp_path / "benchmark.md"
        _export_benchmark(sample_benchmark_report, output_file, "markdown")

        content = output_file.read_text()
        assert "## Per-Index Results" in content
        assert "### test-index" in content
        assert "Documents: 1,000" in content
