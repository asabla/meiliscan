"""FastAPI application for the web dashboard."""

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meiliscan.core.collector import DataCollector
from meiliscan.core.progress import ProgressEvent
from meiliscan.core.reporter import Reporter
from meiliscan.models.monitoring import AlertConfig, MonitoringSnapshot
from meiliscan.models.report import AnalysisReport

# Analysis status type
AnalysisStatus = Literal["idle", "running", "done", "error"]


class AppState:
    """Application state container."""

    def __init__(self):
        self.report: AnalysisReport | None = None
        self.collector: DataCollector | None = None
        self.meili_url: str | None = None
        self.meili_api_key: str | None = None
        self.dump_path: Path | None = None
        self.dump_filename: str | None = None  # Original upload filename
        # Analysis options
        self.probe_search: bool = False
        self.sample_documents: int | None = 20  # None means "all"
        self.detect_sensitive: bool = False
        self.max_concurrent: int = 10  # Concurrent index fetching limit
        # Benchmark options
        self.run_benchmark: bool = False  # Run benchmark after analysis
        self.comprehensive_benchmark: bool = (
            False  # Use comprehensive mode (3 queries per type)
        )
        # Analysis progress tracking
        self.analysis_status: AnalysisStatus = "idle"
        self.analysis_error: str | None = None
        self._progress_subscribers: list[asyncio.Queue[ProgressEvent | None]] = []
        # Benchmark progress tracking (separate from analysis)
        self.benchmark_status: AnalysisStatus = "idle"
        self.benchmark_error: str | None = None
        self._benchmark_subscribers: list[asyncio.Queue[dict | None]] = []
        # Shared live collector for lightweight HTMX requests
        self._live_collector = None
        # Monitoring state
        self.monitoring_enabled: bool = False
        self.monitoring_interval: int = 30  # seconds
        self.monitoring_history: list[MonitoringSnapshot] = []
        self.monitoring_max_history: int = 500
        self.monitoring_alert_config: AlertConfig = AlertConfig()
        self._monitoring_task: asyncio.Task | None = None
        self._monitoring_subscribers: list[asyncio.Queue[dict | None]] = []

    def subscribe_progress(self) -> asyncio.Queue[ProgressEvent | None]:
        """Subscribe to progress events. Returns a queue that will receive events."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        self._progress_subscribers.append(queue)
        return queue

    def unsubscribe_progress(self, queue: asyncio.Queue[ProgressEvent | None]) -> None:
        """Unsubscribe from progress events."""
        if queue in self._progress_subscribers:
            self._progress_subscribers.remove(queue)

    async def emit_progress(self, event: ProgressEvent | None) -> None:
        """Emit a progress event to all subscribers."""
        for queue in self._progress_subscribers:
            try:
                await queue.put(event)
            except Exception:
                pass  # Ignore errors from closed queues

    def subscribe_benchmark_progress(self) -> asyncio.Queue[dict | None]:
        """Subscribe to benchmark progress events."""
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._benchmark_subscribers.append(queue)
        return queue

    def unsubscribe_benchmark_progress(self, queue: asyncio.Queue[dict | None]) -> None:
        """Unsubscribe from benchmark progress events."""
        if queue in self._benchmark_subscribers:
            self._benchmark_subscribers.remove(queue)

    async def emit_benchmark_progress(self, event: dict | None) -> None:
        """Emit a benchmark progress event to all subscribers."""
        for queue in self._benchmark_subscribers:
            try:
                await queue.put(event)
            except Exception:
                pass  # Ignore errors from closed queues

    def subscribe_monitoring(self) -> asyncio.Queue[dict | None]:
        """Subscribe to monitoring snapshot events."""
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._monitoring_subscribers.append(queue)
        return queue

    def unsubscribe_monitoring(self, queue: asyncio.Queue[dict | None]) -> None:
        """Unsubscribe from monitoring events."""
        if queue in self._monitoring_subscribers:
            self._monitoring_subscribers.remove(queue)

    async def emit_monitoring_event(self, event: dict | None) -> None:
        """Emit a monitoring event to all subscribers."""
        for queue in self._monitoring_subscribers:
            try:
                await queue.put(event)
            except Exception:
                pass

    async def start_monitoring(self) -> None:
        """Start the background monitoring loop."""
        if self._monitoring_task and not self._monitoring_task.done():
            return  # Already running

        self.monitoring_enabled = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

    async def stop_monitoring(self) -> None:
        """Stop the background monitoring loop."""
        self.monitoring_enabled = False
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        self._monitoring_task = None

    async def _monitoring_loop(self) -> None:
        """Background loop that polls the MeiliSearch instance."""
        while self.monitoring_enabled:
            try:
                snapshot = await self._take_snapshot()
                if snapshot:
                    self.monitoring_history.append(snapshot)
                    # Trim history if needed
                    if len(self.monitoring_history) > self.monitoring_max_history:
                        self.monitoring_history = self.monitoring_history[
                            -self.monitoring_max_history :
                        ]
                    await self.emit_monitoring_event(snapshot.to_event_dict())
            except Exception:
                pass  # Don't crash the monitoring loop

            await asyncio.sleep(self.monitoring_interval)

    async def _take_snapshot(self) -> MonitoringSnapshot | None:
        """Take a single monitoring snapshot."""
        collector = await self.get_live_collector()
        if not collector:
            return None

        from datetime import datetime

        snapshot = MonitoringSnapshot(timestamp=datetime.utcnow())

        try:
            # Health check with timing
            start = time.perf_counter()
            await collector._client.get("/health")
            snapshot.health_check_ms = (time.perf_counter() - start) * 1000

            # Stats
            stats_resp = await collector._client.get("/stats")
            stats_resp.raise_for_status()
            stats = stats_resp.json()

            total_docs = 0
            is_indexing = False
            for idx_stats in stats.get("indexes", {}).values():
                total_docs += idx_stats.get("numberOfDocuments", 0)
                if idx_stats.get("isIndexing", False):
                    is_indexing = True

            snapshot.total_documents = total_docs
            snapshot.is_indexing = is_indexing

            # Task queue depth
            tasks_resp = await collector._client.get(
                "/tasks", params={"statuses": "enqueued,processing", "limit": 1}
            )
            tasks_resp.raise_for_status()
            tasks_data = tasks_resp.json()
            total_tasks = tasks_data.get("total", 0)

            # Count by status
            enqueued_resp = await collector._client.get(
                "/tasks", params={"statuses": "enqueued", "limit": 1}
            )
            enqueued_data = enqueued_resp.json()
            processing_resp = await collector._client.get(
                "/tasks", params={"statuses": "processing", "limit": 1}
            )
            processing_data = processing_resp.json()

            snapshot.enqueued_tasks = enqueued_data.get("total", 0)
            snapshot.active_tasks = processing_data.get("total", 0)

            # Sample search latency
            # Pick first index from stats
            index_uids = list(stats.get("indexes", {}).keys())
            if index_uids:
                search_start = time.perf_counter()
                await collector._client.post(
                    f"/indexes/{index_uids[0]}/search",
                    json={"q": "", "limit": 1},
                )
                snapshot.search_latency_sample_ms = (
                    time.perf_counter() - search_start
                ) * 1000

        except Exception:
            pass  # Partial snapshot is still useful

        return snapshot

    async def get_live_collector(self):
        """Get or create a persistent LiveInstanceCollector for the current connection.

        Returns None if no live URL is configured or connection fails.
        """
        if not self.meili_url:
            return None

        from meiliscan.collectors.live_instance import LiveInstanceCollector

        if self._live_collector is None:
            self._live_collector = LiveInstanceCollector(
                url=self.meili_url,
                api_key=self.meili_api_key,
            )
            try:
                if not await self._live_collector.connect():
                    self._live_collector = None
                    return None
            except Exception:
                self._live_collector = None
                return None

        return self._live_collector

    async def close_live_collector(self) -> None:
        """Close and discard the shared live collector."""
        if self._live_collector is not None:
            try:
                await self._live_collector.close()
            except Exception:
                pass
            self._live_collector = None


# Template filters - defined before create_app so they're available at registration time


def severity_color(severity: str) -> str:
    """Get CSS color class for severity level."""
    colors = {
        "critical": "red",
        "warning": "yellow",
        "suggestion": "blue",
        "info": "gray",
    }
    return colors.get(severity.lower(), "gray")


def severity_icon(severity: str) -> str:
    """Get icon for severity level."""
    icons = {
        "critical": "🔴",
        "warning": "🟡",
        "suggestion": "🔵",
        "info": "⚪",
    }
    return icons.get(severity.lower(), "⚪")


def format_number(value: int | float) -> str:
    """Format number with thousands separators."""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def trend_icon(trend: str) -> str:
    """Get icon for trend direction."""
    icons = {
        "up": "&#8593;",
        "down": "&#8595;",
        "stable": "&#8596;",
    }
    trend_str = trend.lower() if hasattr(trend, "lower") else str(trend)
    return icons.get(trend_str, "&#8596;")


def trend_color(trend: str) -> str:
    """Get CSS color class for trend direction."""
    colors = {
        "up": "green",
        "down": "red",
        "stable": "blue",
    }
    trend_str = trend.lower() if hasattr(trend, "lower") else str(trend)
    return colors.get(trend_str, "gray")


# Severity order for sorting (lower number = higher priority)
SEVERITY_ORDER = {
    "critical": 0,
    "warning": 1,
    "suggestion": 2,
    "info": 3,
}


def sort_by_severity(findings: list) -> list:
    """Sort findings by severity (critical first, then warning, suggestion, info)."""
    return sorted(
        findings,
        key=lambda f: SEVERITY_ORDER.get(
            f.severity.value.lower()
            if hasattr(f.severity, "value")
            else str(f.severity).lower(),
            4,
        ),
    )


def create_app(
    meili_url: str | None = None,
    meili_api_key: str | None = None,
    dump_path: Path | None = None,
    probe_search: bool = False,
    sample_documents: int | None = 20,
    detect_sensitive: bool = False,
    max_concurrent: int = 10,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        meili_url: MeiliSearch instance URL
        meili_api_key: MeiliSearch API key
        dump_path: Path to dump file for offline analysis
        probe_search: Run read-only search probes to validate sort/filter configuration
        sample_documents: Number of sample documents to fetch per index (None = all)
        detect_sensitive: Enable detection of potential PII/sensitive fields
        max_concurrent: Maximum number of indexes to fetch/parse concurrently

    Returns:
        Configured FastAPI application
    """
    state = AppState()
    state.meili_url = meili_url
    state.meili_api_key = meili_api_key
    state.dump_path = dump_path
    state.probe_search = probe_search
    state.sample_documents = sample_documents
    state.detect_sensitive = detect_sensitive
    state.max_concurrent = max_concurrent

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan manager."""
        # Startup: Run initial analysis if source provided
        if state.meili_url or state.dump_path:
            await run_analysis(state)
        yield
        # Shutdown: Stop monitoring and clean up collectors
        await state.stop_monitoring()
        await state.close_live_collector()
        if state.collector:
            await state.collector.close()

    app = FastAPI(
        title="Meiliscan",
        description="Analyze MeiliSearch instances and dumps for optimization opportunities",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount static files
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Set up templates
    templates_path = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=templates_path)

    # Add custom template filters
    templates.env.filters["severity_color"] = severity_color
    templates.env.filters["severity_icon"] = severity_icon
    templates.env.filters["format_number"] = format_number
    templates.env.filters["trend_icon"] = trend_icon
    templates.env.filters["trend_color"] = trend_color
    templates.env.filters["sort_by_severity"] = sort_by_severity

    # Add global template function to check if connected to live instance
    def is_live_instance() -> bool:
        return state.meili_url is not None

    templates.env.globals["is_live_instance"] = is_live_instance

    # Store state and templates in app
    app.state.analyzer_state = state
    app.state.templates = templates

    # Register routes
    from meiliscan.web.routes import register_routes

    register_routes(app)

    return app


async def run_analysis(state: AppState, emit_done: bool = True) -> None:
    """Run analysis and store results in state.

    Uses the analysis options stored in state:
    - sample_documents: Number of sample documents to fetch per index
    - probe_search: Run search probes (live instance only)
    - detect_sensitive: Enable PII/sensitive field detection
    - max_concurrent: Maximum concurrent index fetching

    Args:
        state: Application state
        emit_done: Whether to emit the done signal (None) when complete.
                   Set to False when chaining with benchmark.
    """
    state.analysis_status = "running"
    state.analysis_error = None

    async def progress_cb(event: ProgressEvent) -> None:
        """Progress callback that emits to all subscribers."""
        await state.emit_progress(event)

    try:
        if state.dump_path:
            state.collector = DataCollector.from_dump(
                state.dump_path,
                max_sample_docs=state.sample_documents,
                max_concurrent=state.max_concurrent,
            )
        elif state.meili_url:
            state.collector = DataCollector.from_url(
                state.meili_url,
                api_key=state.meili_api_key,
                sample_docs=state.sample_documents,
                max_concurrent=state.max_concurrent,
            )
        else:
            state.analysis_status = "idle"
            return

        # Collect data
        if not await state.collector.collect(progress_cb):
            state.analysis_status = "error"
            state.analysis_error = "Failed to collect data from source"
            await state.emit_progress(None)  # Signal completion
            return

        # Build analysis options
        analysis_options: dict = {
            "detect_sensitive": state.detect_sensitive,
            "sample_documents": state.sample_documents,
        }

        # Run search probes if requested (live instance only)
        if state.probe_search and state.meili_url:
            from meiliscan.analyzers.search_probe_analyzer import SearchProbeAnalyzer
            from meiliscan.collectors.live_instance import LiveInstanceCollector

            await state.emit_progress(
                ProgressEvent(phase="analyze", message="Running search probes...")
            )

            probe_analyzer = SearchProbeAnalyzer()

            # Access the underlying LiveInstanceCollector for search
            live_collector = state.collector._collector
            if isinstance(live_collector, LiveInstanceCollector):

                async def search_fn(index_uid, query, filter, sort, facets=None):
                    return await live_collector.search(
                        index_uid=index_uid,
                        query=query,
                        filter=filter,
                        sort=sort,
                        facets=facets,
                    )

                probe_findings, _ = await probe_analyzer.analyze(
                    state.collector.indexes, search_fn
                )
                analysis_options["_probe_findings"] = probe_findings

        # Run analysis
        reporter = Reporter(state.collector, analysis_options=analysis_options)
        state.report = await reporter.generate_report(
            source_url=state.meili_url, progress_cb=progress_cb
        )

        state.analysis_status = "done"
        if emit_done:
            await state.emit_progress(None)  # Signal completion

    except Exception as e:
        # Log error but don't crash - UI will show "no data" state
        state.analysis_status = "error"
        state.analysis_error = str(e)
        await state.emit_progress(None)  # Signal completion
        print(f"Error running analysis: {e}")


async def run_analysis_and_benchmark(state: AppState) -> None:
    """Run analysis and optionally run benchmarks afterwards.

    This is a wrapper around run_analysis that also triggers benchmark
    if state.run_benchmark is True and we're connected to a live instance.

    Progress events are emitted through the analysis channel so the dashboard
    progress modal can track both analysis and benchmark phases before reloading.
    """
    # Check if we'll need to run benchmark after
    will_benchmark = state.run_benchmark and state.meili_url

    # Run analysis, but don't emit done signal if we'll benchmark after
    await run_analysis(state, emit_done=not will_benchmark)

    # If analysis succeeded and auto-benchmark is enabled, run benchmarks
    if state.analysis_status == "done" and will_benchmark and state.report:
        await run_benchmark_after_analysis(state)
        # Now emit the done signal after benchmark completes
        await state.emit_progress(None)
    # If analysis failed or no benchmark needed, done signal already emitted by run_analysis


async def run_benchmark_after_analysis(state: AppState) -> None:
    """Run benchmarks after a successful analysis.

    Emits progress through the analysis channel (emit_progress) so the
    dashboard progress modal can show benchmark progress before reloading.
    """
    from meiliscan.benchmarks.search_runner import SearchBenchmarkRunner
    from meiliscan.collectors.live_instance import LiveInstanceCollector

    state.benchmark_status = "running"
    state.benchmark_error = None

    try:
        await state.emit_progress(
            ProgressEvent(phase="benchmark", message="Starting benchmarks...")
        )

        # Create a collector for benchmarking
        meili_url = state.meili_url
        if not meili_url:
            state.benchmark_status = "error"
            state.benchmark_error = "No MeiliSearch URL configured"
            return

        collector = LiveInstanceCollector(
            url=meili_url,
            api_key=state.meili_api_key,
        )

        try:
            if not await collector.connect():
                state.benchmark_status = "error"
                state.benchmark_error = "Failed to connect to MeiliSearch"
                return

            await state.emit_progress(
                ProgressEvent(phase="benchmark", message="Fetching index data...")
            )

            # Fetch index data for benchmarking
            all_indexes = await collector.get_indexes()

            # Filter to only the indexes we analyzed
            index_uids = set(state.report.indexes.keys()) if state.report else set()
            index_data_list = [idx for idx in all_indexes if idx.uid in index_uids]

            if not index_data_list:
                state.benchmark_status = "error"
                state.benchmark_error = "No indexes to benchmark"
                return

            total_indexes = len(index_data_list)
            await state.emit_progress(
                ProgressEvent(
                    phase="benchmark",
                    message=f"Running benchmarks on {total_indexes} index(es)...",
                    total=total_indexes,
                    current=0,
                )
            )

            # Create progress callback for the benchmark runner
            current_index = [0]  # Use list for mutable closure

            async def benchmark_progress_cb(index_uid: str, query_type: str) -> None:
                await state.emit_progress(
                    ProgressEvent(
                        phase="benchmark",
                        message=f"Benchmarking {index_uid}: {query_type}",
                        index_uid=index_uid,
                        current=current_index[0],
                        total=total_indexes,
                    )
                )

            async def index_complete_cb(index_uid: str) -> None:
                current_index[0] += 1
                await state.emit_progress(
                    ProgressEvent(
                        phase="benchmark",
                        message=f"Completed {index_uid} ({current_index[0]}/{total_indexes})",
                        index_uid=index_uid,
                        current=current_index[0],
                        total=total_indexes,
                    )
                )

            # Run benchmarks with mode based on settings
            runner = SearchBenchmarkRunner(
                collector=collector,
                queries_per_type=3 if state.comprehensive_benchmark else 1,
                progress_cb=benchmark_progress_cb,
                index_complete_cb=index_complete_cb,
            )

            # Use comprehensive or baseline based on setting
            if state.comprehensive_benchmark:
                benchmark_report = await runner.run_comprehensive(index_data_list)
            else:
                benchmark_report = await runner.run_baseline(index_data_list)

            # Store in report
            if state.report:
                state.report.benchmark = benchmark_report

            state.benchmark_status = "done"
            await state.emit_progress(
                ProgressEvent(phase="benchmark", message="Benchmark complete!")
            )

        finally:
            await collector.close()

    except Exception as e:
        state.benchmark_status = "error"
        state.benchmark_error = str(e)
        print(f"Error running auto-benchmark: {e}")
