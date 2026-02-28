"""Benchmark route definitions."""

import asyncio
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from sse_starlette.sse import EventSourceResponse

from meiliscan.web.app import AppState
from meiliscan.web.routes._shared import sort_findings_by_severity


def register_benchmark_routes(app: FastAPI) -> None:
    """Register benchmark routes (HTML pages and API endpoints)."""

    @app.get("/benchmark", response_class=HTMLResponse)
    async def benchmark_page(request: Request):
        """Render the benchmark page (live instances only)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        is_live = bool(state.meili_url)

        # Get findings that have fixes (for fix benchmark UI)
        fixable_findings = []
        if state.report:
            all_findings = state.report.get_all_findings()
            fixable_findings = [f for f in all_findings if f.fix and f.index_uid]
            # Sort by severity
            fixable_findings = sort_findings_by_severity(fixable_findings)

        return templates.TemplateResponse(
            "benchmark.html",
            {
                "request": request,
                "report": state.report,
                "is_live": is_live,
                "benchmark": state.report.benchmark if state.report else None,
                "fixable_findings": fixable_findings,
                "benchmark_status": state.benchmark_status,
                "benchmark_error": state.benchmark_error,
            },
        )

    @app.get("/benchmark/results", response_class=HTMLResponse)
    async def benchmark_results_partial(request: Request):
        """HTMX partial for benchmark results."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        return templates.TemplateResponse(
            "components/benchmark_results.html",
            {
                "request": request,
                "benchmark": state.report.benchmark if state.report else None,
            },
        )

    @app.post("/benchmark/fix/{finding_id}", response_class=HTMLResponse)
    async def benchmark_fix_partial(
        request: Request,
        finding_id: str,
        apply: bool = False,
        revert_after: bool = True,
    ):
        """Run fix benchmark and return HTML partial result."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        error: str | None = None
        result = None

        # Gate apply=True behind an environment variable for safety
        if apply and not os.environ.get("MEILISCAN_ALLOW_APPLY_FIX"):
            error = (
                "Applying fixes is disabled by default. "
                "Set MEILISCAN_ALLOW_APPLY_FIX=1 to enable."
            )
        # Benchmarks only work on live instances
        elif not state.meili_url:
            error = "Fix benchmarks require a live MeiliSearch instance"
        elif not state.report:
            error = "No analysis data available. Run analysis first."
        else:
            # Find the finding
            all_findings = state.report.get_all_findings()
            finding = next((f for f in all_findings if f.id == finding_id), None)

            if not finding:
                error = f"Finding {finding_id} not found"
            elif not finding.fix:
                error = f"Finding {finding_id} has no fix defined"
            elif not finding.index_uid:
                error = f"Finding {finding_id} is not index-specific"
            elif finding.index_uid not in state.report.indexes:
                error = f"Index {finding.index_uid} not found in report"
            else:
                from meiliscan.benchmarks.fix_benchmark import FixBenchmarkRunner
                from meiliscan.collectors.live_instance import LiveInstanceCollector

                collector = LiveInstanceCollector(
                    url=state.meili_url,
                    api_key=state.meili_api_key,
                )

                try:
                    if not await collector.connect():
                        error = "Failed to connect to MeiliSearch instance"
                    else:
                        # Fetch fresh index data
                        all_indexes = await collector.get_indexes()
                        index_data = next(
                            (
                                idx
                                for idx in all_indexes
                                if idx.uid == finding.index_uid
                            ),
                            None,
                        )
                        if not index_data:
                            error = (
                                f"Failed to fetch index data for {finding.index_uid}"
                            )
                        else:
                            runner = FixBenchmarkRunner(collector=collector)
                            result = await runner.benchmark_fix(
                                index=index_data,
                                finding=finding,
                                apply=apply,
                                revert_after=revert_after,
                            )
                except Exception as e:
                    error = f"Fix benchmark failed: {e}"
                finally:
                    await collector.close()

        return templates.TemplateResponse(
            "components/fix_benchmark_result.html",
            {
                "request": request,
                "error": error,
                "result": result,
                "finding_id": finding_id,
            },
        )

    # ==================== Benchmark API Routes ====================

    @app.get("/api/benchmark")
    async def api_get_benchmark(request: Request) -> dict:
        """Get existing benchmark results from the report."""
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return {"error": "No analysis data available"}

        if not state.report.benchmark:
            return {"error": "No benchmark results available", "available": False}

        return {
            "available": True,
            "benchmark": state.report.benchmark.model_dump(),
        }

    @app.post("/api/benchmark")
    async def api_run_benchmark(
        request: Request,
        comprehensive: bool = False,
    ) -> dict:
        """Run benchmarks against the live instance.

        Args:
            comprehensive: If True, run more queries per type for more accurate results

        Returns:
            BenchmarkReport with results
        """
        state: AppState = request.app.state.analyzer_state

        # Benchmarks only work on live instances
        if not state.meili_url:
            return {
                "error": "Benchmarks require a live MeiliSearch instance",
                "available": False,
            }

        if not state.report:
            return {"error": "No analysis data available. Run analysis first."}

        # Check if already running
        if state.benchmark_status == "running":
            return {"error": "Benchmark already running"}

        from meiliscan.benchmarks.search_runner import SearchBenchmarkRunner
        from meiliscan.collectors.live_instance import LiveInstanceCollector

        # Set status to running
        state.benchmark_status = "running"
        state.benchmark_error = None

        # Create a collector for benchmarking
        collector = LiveInstanceCollector(
            url=state.meili_url,
            api_key=state.meili_api_key,
        )

        try:
            await state.emit_benchmark_progress(
                {"phase": "benchmark", "message": "Connecting to MeiliSearch..."}
            )

            if not await collector.connect():
                state.benchmark_status = "error"
                state.benchmark_error = "Failed to connect to MeiliSearch instance"
                await state.emit_benchmark_progress(None)  # Signal completion
                return {"error": "Failed to connect to MeiliSearch instance"}

            await state.emit_benchmark_progress(
                {"phase": "benchmark", "message": "Fetching index data..."}
            )

            # Fetch index data for benchmarking
            # We need fresh IndexData objects with settings for query generation
            all_indexes = await collector.get_indexes()

            # Filter to only the indexes we analyzed
            index_uids = set(state.report.indexes.keys())
            index_data_list = [idx for idx in all_indexes if idx.uid in index_uids]

            if not index_data_list:
                state.benchmark_status = "error"
                state.benchmark_error = "No indexes to benchmark"
                await state.emit_benchmark_progress(None)  # Signal completion
                return {"error": "No indexes to benchmark"}

            total_indexes = len(index_data_list)
            await state.emit_benchmark_progress(
                {
                    "phase": "benchmark",
                    "message": f"Running benchmarks on {total_indexes} index(es)...",
                    "total": total_indexes,
                    "current": 0,
                }
            )

            # Create progress callback for the benchmark runner
            current_index = [0]  # Use list for mutable closure

            async def benchmark_progress_cb(index_uid: str, query_type: str) -> None:
                """Progress callback for benchmark runner."""
                await state.emit_benchmark_progress(
                    {
                        "phase": "benchmark",
                        "message": f"Benchmarking {index_uid}: {query_type}",
                        "index_uid": index_uid,
                        "current": current_index[0],
                        "total": total_indexes,
                    }
                )

            async def index_complete_cb(index_uid: str) -> None:
                """Callback when an index benchmark completes."""
                current_index[0] += 1
                await state.emit_benchmark_progress(
                    {
                        "phase": "benchmark",
                        "message": f"Completed {index_uid} ({current_index[0]}/{total_indexes})",
                        "index_uid": index_uid,
                        "current": current_index[0],
                        "total": total_indexes,
                    }
                )

            # Run benchmarks
            runner = SearchBenchmarkRunner(
                collector=collector,
                queries_per_type=3 if comprehensive else 1,
                progress_cb=benchmark_progress_cb,
                index_complete_cb=index_complete_cb,
            )

            if comprehensive:
                benchmark_report = await runner.run_comprehensive(index_data_list)
            else:
                benchmark_report = await runner.run_baseline(index_data_list)

            # Store in report for later retrieval
            state.report.benchmark = benchmark_report

            state.benchmark_status = "done"
            await state.emit_benchmark_progress(
                {"phase": "benchmark", "message": "Benchmark complete!"}
            )
            await state.emit_benchmark_progress(None)  # Signal completion

            return {
                "success": True,
                "benchmark": benchmark_report.model_dump(),
            }

        except Exception as e:
            state.benchmark_status = "error"
            state.benchmark_error = str(e)
            await state.emit_benchmark_progress(None)  # Signal completion
            return {"error": f"Benchmark failed: {e}"}
        finally:
            await collector.close()

    @app.get("/api/benchmark/export")
    async def api_export_benchmark(
        request: Request,
        format: str = "json",
    ) -> Response:
        """Download benchmark results separately.

        Args:
            format: Export format - json or markdown

        Returns:
            The benchmark results as a downloadable file
        """
        state: AppState = request.app.state.analyzer_state

        if not state.report or not state.report.benchmark:
            return Response(
                content=json.dumps({"error": "No benchmark results available"}),
                media_type="application/json",
                status_code=400,
            )

        benchmark = state.report.benchmark

        if format.lower() == "markdown":
            # Generate markdown report
            lines = [
                "# MeiliSearch Benchmark Report",
                "",
                f"**Run at:** {benchmark.ran_at.isoformat()}",
                f"**Source:** {benchmark.source_url}",
                f"**Duration:** {benchmark.duration_ms:.2f}ms",
                f"**Total Queries:** {benchmark.total_queries}",
                "",
                "## Summary",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Avg Baseline | {benchmark.avg_baseline_ms:.2f}ms |",
                f"| Avg Overall | {benchmark.avg_overall_ms:.2f}ms |",
                f"| P50 Latency | {benchmark.p50_latency_ms:.2f}ms |",
                f"| P95 Latency | {benchmark.p95_latency_ms:.2f}ms |",
                f"| P99 Latency | {benchmark.p99_latency_ms:.2f}ms |",
                f"| Min Latency | {benchmark.min_latency_ms:.2f}ms |",
                f"| Max Latency | {benchmark.max_latency_ms:.2f}ms |",
                "",
                "## Per-Index Results",
                "",
            ]

            for idx_bench in benchmark.indexes:
                lines.extend(
                    [
                        f"### {idx_bench.index_uid}",
                        "",
                        f"- Documents: {idx_bench.document_count:,}",
                        f"- Baseline Latency: {idx_bench.baseline_latency_ms:.2f}ms",
                    ]
                )
                if idx_bench.filtered_latency_ms is not None:
                    lines.append(
                        f"- Filtered Latency: {idx_bench.filtered_latency_ms:.2f}ms"
                    )
                if idx_bench.sorted_latency_ms is not None:
                    lines.append(
                        f"- Sorted Latency: {idx_bench.sorted_latency_ms:.2f}ms"
                    )
                lines.append("")

            if benchmark.slowest_queries:
                lines.extend(["## Slowest Queries", ""])
                for i, q in enumerate(benchmark.slowest_queries[:5], 1):
                    lines.append(
                        f"{i}. **{q.index_uid}** - {q.query.query_type}: {q.latency_ms:.2f}ms"
                    )
                lines.append("")

            content = "\n".join(lines)
            media_type = "text/markdown"
            ext = ".md"
        else:
            # JSON format
            content = json.dumps(benchmark.model_dump(), indent=2, default=str)
            media_type = "application/json"
            ext = ".json"

        timestamp = benchmark.ran_at.strftime("%Y%m%d_%H%M%S")
        filename = f"meilisearch-benchmark_{timestamp}{ext}"

        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.post("/api/benchmark/fix/{finding_id}")
    async def api_benchmark_fix(
        request: Request,
        finding_id: str,
        apply: bool = False,
        revert_after: bool = True,
    ) -> dict:
        """Benchmark a specific fix, optionally applying it.

        WARNING: If apply=True, this will modify your MeiliSearch instance settings!

        Args:
            finding_id: The ID of the finding to benchmark (e.g., MEILI-S001)
            apply: If True, actually apply the fix (MODIFIES YOUR INSTANCE!)
            revert_after: If True and apply=True, revert settings after benchmarking

        Returns:
            FixBenchmark with before/after results
        """
        state: AppState = request.app.state.analyzer_state

        # Gate apply=True behind an environment variable for safety
        if apply and not os.environ.get("MEILISCAN_ALLOW_APPLY_FIX"):
            return {
                "error": (
                    "Applying fixes is disabled by default. "
                    "Set MEILISCAN_ALLOW_APPLY_FIX=1 to enable."
                ),
            }

        # Benchmarks only work on live instances
        if not state.meili_url:
            return {
                "error": "Fix benchmarks require a live MeiliSearch instance",
            }

        if not state.report:
            return {"error": "No analysis data available. Run analysis first."}

        # Find the finding
        all_findings = state.report.get_all_findings()
        finding = next((f for f in all_findings if f.id == finding_id), None)

        if not finding:
            return {"error": f"Finding {finding_id} not found"}

        if not finding.fix:
            return {"error": f"Finding {finding_id} has no fix defined"}

        if not finding.index_uid:
            return {"error": f"Finding {finding_id} is not index-specific"}

        # Get the index
        if finding.index_uid not in state.report.indexes:
            return {"error": f"Index {finding.index_uid} not found in report"}

        from meiliscan.benchmarks.fix_benchmark import FixBenchmarkRunner
        from meiliscan.collectors.live_instance import LiveInstanceCollector

        collector = LiveInstanceCollector(
            url=state.meili_url,
            api_key=state.meili_api_key,
        )

        try:
            if not await collector.connect():
                return {"error": "Failed to connect to MeiliSearch instance"}

            # Fetch fresh index data for the specific index
            all_indexes = await collector.get_indexes()
            index_data = next(
                (idx for idx in all_indexes if idx.uid == finding.index_uid), None
            )
            if not index_data:
                return {"error": f"Failed to fetch index data for {finding.index_uid}"}

            runner = FixBenchmarkRunner(collector=collector)
            result = await runner.benchmark_fix(
                index=index_data,
                finding=finding,
                apply=apply,
                revert_after=revert_after,
            )

            return {
                "success": True,
                "applied": result.applied,
                "reverted": result.reverted,
                "fix_benchmark": result.model_dump(),
            }

        except Exception as e:
            return {"error": f"Fix benchmark failed: {e}"}
        finally:
            await collector.close()

    @app.get("/api/benchmark/events")
    async def api_benchmark_events(request: Request):
        """Server-Sent Events endpoint for benchmark progress.

        Streams progress events during benchmarking. Events are JSON objects with:
        - phase: "benchmark"
        - message: Human-readable status message
        - current: Current item number (optional)
        - total: Total items (optional)
        - index_uid: Index being benchmarked (optional)

        A final event with data: null signals completion.
        """
        state: AppState = request.app.state.analyzer_state

        async def event_generator():
            """Generate SSE events from benchmark progress queue."""
            queue = state.subscribe_benchmark_progress()
            try:
                # Send initial status
                yield {
                    "event": "status",
                    "data": json.dumps(
                        {
                            "status": state.benchmark_status,
                            "error": state.benchmark_error,
                        }
                    ),
                }

                # If benchmark is not running, wait a bit for it to start
                if state.benchmark_status != "running":
                    # Wait up to 5 seconds for benchmark to start
                    for _ in range(50):
                        await asyncio.sleep(0.1)
                        if state.benchmark_status == "running":
                            break

                    # If still not running, return current status
                    if state.benchmark_status != "running":
                        yield {
                            "event": "done",
                            "data": json.dumps(
                                {
                                    "status": state.benchmark_status,
                                    "has_results": (
                                        state.report is not None
                                        and state.report.benchmark is not None
                                    ),
                                }
                            ),
                        }
                        return

                # Stream progress events
                while True:
                    try:
                        # Wait for next event with timeout
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)

                        if event is None:
                            # None signals completion
                            yield {
                                "event": "done",
                                "data": json.dumps(
                                    {
                                        "status": state.benchmark_status,
                                        "error": state.benchmark_error,
                                        "has_results": (
                                            state.report is not None
                                            and state.report.benchmark is not None
                                        ),
                                    }
                                ),
                            }
                            break

                        # Send progress event
                        yield {
                            "event": "progress",
                            "data": json.dumps(event),
                        }

                    except asyncio.TimeoutError:
                        # Send heartbeat to keep connection alive
                        yield {"event": "heartbeat", "data": ""}

            finally:
                state.unsubscribe_benchmark_progress(queue)

        return EventSourceResponse(event_generator())
