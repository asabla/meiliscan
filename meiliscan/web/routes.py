"""Route definitions for the web dashboard."""

import asyncio
import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sse_starlette.sse import EventSourceResponse

from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.exporters.agent_exporter import AgentExporter
from meiliscan.exporters.json_exporter import JsonExporter
from meiliscan.exporters.markdown_exporter import MarkdownExporter
from meiliscan.exporters.sarif_exporter import SarifExporter
from meiliscan.models.report import AnalysisReport
from meiliscan.web.app import AppState, run_analysis, run_analysis_and_benchmark

# Valid export formats
EXPORT_FORMATS = ("json", "markdown", "sarif", "agent")

# Severity order for sorting (lower number = higher priority)
SEVERITY_ORDER = {
    "critical": 0,
    "warning": 1,
    "suggestion": 2,
    "info": 3,
}


def sort_findings_by_severity(findings: list) -> list:
    """Sort findings by severity (critical first, then warning, suggestion, info)."""
    return sorted(
        findings,
        key=lambda f: SEVERITY_ORDER.get(f.severity.value.lower(), 4),
    )


def register_routes(app: FastAPI) -> None:
    """Register all routes for the application."""

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Render the main dashboard."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        from meiliscan.models.task import Task, TasksSummary

        # Get tasks summary if we have a collector
        tasks_summary: TasksSummary | None = None
        if state.collector:
            try:
                raw_tasks = await state.collector.get_tasks(limit=100)
                tasks = [Task(**t) for t in raw_tasks]
                tasks_summary = TasksSummary.from_tasks(tasks)
            except Exception:
                pass

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "report": state.report,
                "source_url": state.meili_url,
                "source_dump": state.dump_path,
                "tasks_summary": tasks_summary,
                # Analysis options
                "probe_search": state.probe_search,
                "sample_documents": state.sample_documents,
                "detect_sensitive": state.detect_sensitive,
            },
        )

    @app.get("/index/{index_uid}", response_class=HTMLResponse)
    async def index_detail(request: Request, index_uid: str):
        """Render index detail page."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        index_analysis = None
        if state.report and index_uid in state.report.indexes:
            index_analysis = state.report.indexes[index_uid]

        return templates.TemplateResponse(
            "index_detail.html",
            {
                "request": request,
                "report": state.report,
                "index_uid": index_uid,
                "index_analysis": index_analysis,
            },
        )

    @app.get("/findings", response_class=HTMLResponse)
    async def findings_explorer(
        request: Request,
        severity: str | None = None,
        category: str | None = None,
        index: str | None = None,
    ):
        """Render findings explorer page."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        # Get all findings
        all_findings = []
        if state.report:
            all_findings = state.report.get_all_findings()

        # Filter findings
        filtered = all_findings
        if severity:
            filtered = [
                f for f in filtered if f.severity.value.lower() == severity.lower()
            ]
        if category:
            filtered = [
                f for f in filtered if f.category.value.lower() == category.lower()
            ]
        if index:
            filtered = [f for f in filtered if f.index_uid == index]

        # Sort by severity (critical first)
        filtered = sort_findings_by_severity(filtered)

        # Get unique categories and indexes for filters
        categories = sorted(set(f.category.value for f in all_findings))
        indexes = sorted(set(f.index_uid for f in all_findings if f.index_uid))

        # Count findings by severity for display
        severity_counts = {
            "critical": sum(
                1 for f in all_findings if f.severity.value.lower() == "critical"
            ),
            "warning": sum(
                1 for f in all_findings if f.severity.value.lower() == "warning"
            ),
            "suggestion": sum(
                1 for f in all_findings if f.severity.value.lower() == "suggestion"
            ),
            "info": sum(1 for f in all_findings if f.severity.value.lower() == "info"),
        }

        return templates.TemplateResponse(
            "findings.html",
            {
                "request": request,
                "report": state.report,
                "findings": filtered,
                "categories": categories,
                "indexes": indexes,
                "current_severity": severity,
                "current_category": category,
                "current_index": index,
                "severity_counts": severity_counts,
            },
        )

    @app.get("/findings/list", response_class=HTMLResponse)
    async def findings_list_partial(
        request: Request,
        severity: str | None = None,
        category: str | None = None,
        index: str | None = None,
    ):
        """Render findings list partial (HTMX) for dynamic filtering."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        # Get all findings
        all_findings = []
        if state.report:
            all_findings = state.report.get_all_findings()

        # Filter findings
        filtered = all_findings
        if severity:
            filtered = [
                f for f in filtered if f.severity.value.lower() == severity.lower()
            ]
        if category:
            filtered = [
                f for f in filtered if f.category.value.lower() == category.lower()
            ]
        if index:
            filtered = [f for f in filtered if f.index_uid == index]

        # Sort by severity (critical first)
        filtered = sort_findings_by_severity(filtered)

        return templates.TemplateResponse(
            "components/findings_list.html",
            {
                "request": request,
                "findings": filtered,
                "current_severity": severity,
                "current_category": category,
                "current_index": index,
            },
        )

    @app.get("/finding/{finding_id}", response_class=HTMLResponse)
    async def finding_detail(request: Request, finding_id: str):
        """Render finding detail (HTMX partial)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        finding = None
        if state.report:
            all_findings = state.report.get_all_findings()
            finding = next((f for f in all_findings if f.id == finding_id), None)

        return templates.TemplateResponse(
            "components/finding_detail.html",
            {
                "request": request,
                "finding": finding,
            },
        )

    @app.get("/search", response_class=HTMLResponse)
    async def search_playground(request: Request, index: str | None = None):
        """Render search playground page (live instances only)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        is_live = bool(state.meili_url)
        meili_url = state.meili_url
        indexes: list[str] = []
        selected_index: str | None = None
        index_settings: dict | None = None

        if is_live and meili_url:
            from meiliscan.collectors.live_instance import LiveInstanceCollector

            collector = LiveInstanceCollector(
                url=meili_url,
                api_key=state.meili_api_key,
            )
            try:
                if await collector.connect():
                    # Use lightweight method - only fetches UIDs, not full index data
                    indexes = await collector.list_index_uids()

                    selected_index = index or (indexes[0] if indexes else None)
                    if selected_index:
                        # Fetch settings only for the selected index
                        index_settings = await collector.get_index_settings(
                            selected_index
                        )
            finally:
                await collector.close()

        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "is_live": is_live,
                "indexes": indexes,
                "selected_index": selected_index,
                "index_settings": index_settings,
            },
        )

    @app.get("/search/{index_uid}/settings", response_class=HTMLResponse)
    async def search_index_settings(request: Request, index_uid: str):
        """Fetch index settings partial for HTMX (lazy loading on index change)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        index_settings: dict | None = None

        if state.meili_url:
            from meiliscan.collectors.live_instance import LiveInstanceCollector

            collector = LiveInstanceCollector(
                url=state.meili_url,
                api_key=state.meili_api_key,
            )
            try:
                if await collector.connect():
                    index_settings = await collector.get_index_settings(index_uid)
            finally:
                await collector.close()

        return templates.TemplateResponse(
            "components/search_index_info.html",
            {
                "request": request,
                "index_settings": index_settings,
                "selected_index": index_uid,
            },
        )

    @app.post("/search/{index_uid}/results", response_class=HTMLResponse)
    async def search_results(
        request: Request,
        index_uid: str,
        q: str = Form(default=""),
        filter: str = Form(default=""),
        sort_field: str = Form(default=""),
        sort_direction: str = Form(default="asc"),
        distinct: str = Form(default=""),
        hitsPerPage: int = Form(default=20),
        page: int = Form(default=1),
    ):
        """Perform a live search and return results partial (HTMX)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        if not state.meili_url:
            return templates.TemplateResponse(
                "components/search_results.html",
                {
                    "request": request,
                    "error": "Live connection required for search",
                    "results": None,
                    "search_params": {},
                },
            )

        from meiliscan.collectors.live_instance import LiveInstanceCollector

        error: str | None = None
        results: dict | None = None

        hits_per_page = max(1, min(int(hitsPerPage), 1000))
        page_num = max(1, int(page))

        filter_expr: str | None = filter.strip() or None
        sort: list[str] | None = (
            [f"{sort_field.strip()}:{sort_direction}"] if sort_field.strip() else None
        )
        distinct_attr: str | None = distinct.strip() or None

        search_params: dict[str, object] = {
            "q": q,
            "hitsPerPage": hits_per_page,
            "page": page_num,
        }
        if filter_expr:
            search_params["filter"] = filter_expr
        if sort:
            search_params["sort"] = sort
        if distinct_attr:
            search_params["distinct"] = distinct_attr

        meili_url = state.meili_url
        if not meili_url:
            return templates.TemplateResponse(
                "components/search_results.html",
                {
                    "request": request,
                    "error": "Live connection required for search",
                    "results": None,
                    "search_params": {},
                },
            )

        collector = LiveInstanceCollector(
            url=meili_url,
            api_key=state.meili_api_key,
        )
        try:
            if not await collector.connect():
                error = "Failed to connect to MeiliSearch instance"
            else:
                results = await collector.search(
                    index_uid=index_uid,
                    query=q,
                    filter=filter_expr,
                    sort=sort,
                    page=page_num,
                    hits_per_page=hits_per_page,
                    distinct=distinct_attr,
                )
        except Exception as e:
            error = str(e)
        finally:
            await collector.close()

        return templates.TemplateResponse(
            "components/search_results.html",
            {
                "request": request,
                "error": error,
                "results": results,
                "search_params": search_params,
            },
        )

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

        # Benchmarks only work on live instances
        if not state.meili_url:
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

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(
        request: Request,
        status: str | None = None,
        task_type: str | None = None,
        index: str | None = None,
    ):
        """Render tasks queue page."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        from meiliscan.models.task import Task, TasksSummary

        error: str | None = None
        tasks_summary: TasksSummary | None = None
        indexes: list[str] = []

        if not state.meili_url and not state.collector:
            error = "No data source configured"
        else:
            try:
                raw_tasks = []
                if state.collector:
                    raw_tasks = await state.collector.get_tasks(limit=1000)
                tasks = [Task(**t) for t in raw_tasks]
                tasks_summary = TasksSummary.from_tasks(tasks)
                indexes = sorted({t.index_uid for t in tasks if t.index_uid})
            except Exception as e:
                error = str(e)

        return templates.TemplateResponse(
            "tasks.html",
            {
                "request": request,
                "is_live": bool(state.meili_url),
                "error": error,
                "summary": tasks_summary,
                "indexes": indexes,
                "current_status": status,
                "current_type": task_type,
                "current_index": index,
            },
        )

    @app.get("/tasks/list", response_class=HTMLResponse)
    async def tasks_list_partial(
        request: Request,
        status: str | None = None,
        task_type: str | None = None,
        index: str | None = None,
        from_uid: int | None = None,
        limit: int = 100,
    ):
        """Render tasks table partial (HTMX)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        from meiliscan.models.task import Task

        if not state.collector:
            return templates.TemplateResponse(
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": [],
                    "error": "No tasks available (no collector)",
                    "next_uid": None,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )

        try:
            raw_tasks = await state.collector.get_tasks(limit=1000)
            tasks = [Task(**t) for t in raw_tasks]

            filtered = tasks
            if status:
                filtered = [t for t in filtered if t.status.value == status]
            if task_type:
                filtered = [t for t in filtered if t.task_type == task_type]
            if index:
                filtered = [t for t in filtered if t.index_uid == index]

            filtered.sort(key=lambda t: t.uid, reverse=True)

            if from_uid is not None:
                filtered = [t for t in filtered if t.uid < from_uid]

            page = filtered[:limit]
            next_uid_val = page[-1].uid if len(page) == limit else None

            return templates.TemplateResponse(
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": page,
                    "error": None,
                    "next_uid": next_uid_val,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )
        except Exception as e:
            return templates.TemplateResponse(
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": [],
                    "error": str(e),
                    "next_uid": None,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )

    @app.post("/connect")
    async def connect_instance(
        request: Request,
        background_tasks: BackgroundTasks,
        url: str = Form(...),
        api_key: str = Form(default=""),
        probe_search: str = Form(default=""),
        sample_documents: int = Form(default=20),
        sample_all: str = Form(default=""),
        detect_sensitive: str = Form(default=""),
        run_benchmark: str = Form(default=""),
    ):
        """Connect to a MeiliSearch instance."""
        state: AppState = request.app.state.analyzer_state

        # Update connection info
        state.meili_url = url
        state.meili_api_key = api_key if api_key else None
        state.dump_path = None

        # Update analysis options
        # HTML checkboxes submit their value only when checked, empty string otherwise
        state.probe_search = probe_search == "true"
        state.detect_sensitive = detect_sensitive == "true"
        state.run_benchmark = run_benchmark == "true"

        # Handle sample_all checkbox - if checked, set to None (all docs)
        if sample_all == "true":
            state.sample_documents = None
        else:
            state.sample_documents = max(
                1, min(sample_documents, 10000)
            )  # Validate range

        # Close existing collector
        if state.collector:
            await state.collector.close()

        # Check if this is an AJAX request (from our progress modal JS)
        accept_header = request.headers.get("accept", "")
        is_ajax = "application/json" in accept_header

        if is_ajax:
            # For AJAX requests: run analysis in background, return immediately
            background_tasks.add_task(run_analysis_and_benchmark, state)
            return JSONResponse({"status": "started"})
        else:
            # For regular form submissions: run analysis and redirect
            await run_analysis(state)
            return RedirectResponse(url="/", status_code=303)

    @app.post("/upload")
    async def upload_dump(
        request: Request,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        sample_documents: int = Form(default=20),
        sample_all: str = Form(default=""),
        detect_sensitive: str = Form(default=""),
    ):
        """Upload and analyze a dump file."""
        import tempfile

        state: AppState = request.app.state.analyzer_state

        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # Update connection info
        state.dump_path = tmp_path
        state.meili_url = None
        state.meili_api_key = None

        # Update analysis options (probe_search not applicable for dumps)
        state.probe_search = False
        state.detect_sensitive = detect_sensitive == "true"

        # Handle sample_all checkbox - if checked, set to None (all docs)
        if sample_all == "true":
            state.sample_documents = None
        else:
            state.sample_documents = max(
                1, min(sample_documents, 10000)
            )  # Validate range

        # Close existing collector
        if state.collector:
            await state.collector.close()

        # Check if this is an AJAX request (from our progress modal JS)
        accept_header = request.headers.get("accept", "")
        is_ajax = "application/json" in accept_header

        if is_ajax:
            # For AJAX requests: run analysis in background, return immediately
            background_tasks.add_task(run_analysis, state)
            return JSONResponse({"status": "started"})
        else:
            # For regular form submissions: run analysis and redirect
            await run_analysis(state)
            return RedirectResponse(url="/", status_code=303)

    @app.post("/refresh", response_class=HTMLResponse)
    async def refresh_analysis(request: Request):
        """Re-run analysis with current source."""
        state: AppState = request.app.state.analyzer_state

        if state.collector:
            await state.collector.close()

        await run_analysis(state)

        return RedirectResponse(url="/", status_code=303)

    @app.post("/disconnect", response_class=HTMLResponse)
    async def disconnect(request: Request):
        """Disconnect from current source and reset to initial state."""
        state: AppState = request.app.state.analyzer_state

        # Close existing collector
        if state.collector:
            await state.collector.close()

        # Reset all state
        state.report = None
        state.collector = None
        state.meili_url = None
        state.meili_api_key = None
        state.dump_path = None

        return RedirectResponse(url="/", status_code=303)

    @app.get("/api/report")
    async def api_report(request: Request) -> dict:
        """Get the full report as JSON."""
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return {"error": "No analysis data available"}

        return state.report.to_dict()

    @app.get("/api/health")
    async def api_health(request: Request) -> dict:
        """Get health summary."""
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return {"status": "no_data"}

        # Use configuration coverage from statistics if available
        coverage = 0
        if state.report.statistics:
            coverage = state.report.statistics.overall_coverage_percent

        return {
            "status": "ok",
            "configuration_coverage": coverage,
            "total_indexes": state.report.summary.total_indexes,
            "total_documents": state.report.summary.total_documents,
            "critical_issues": state.report.summary.critical_issues,
            "warnings": state.report.summary.warnings,
        }

    @app.get("/api/statistics")
    async def api_statistics(request: Request) -> dict:
        """Get instance statistics including configuration coverage."""
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return {"error": "No analysis data available"}

        if not state.report.statistics:
            return {"error": "No statistics available"}

        return state.report.statistics.model_dump()

    # ==================== Benchmark Routes ====================

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

    @app.get("/api/export")
    async def api_export(request: Request, format: str = "json") -> Response:
        """Export the analysis report in various formats.

        Args:
            format: Export format - json, markdown, sarif, or agent

        Returns:
            The exported report as a downloadable file
        """
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return Response(
                content=json.dumps({"error": "No analysis data available"}),
                media_type="application/json",
                status_code=400,
            )

        # Validate format
        format_lower = format.lower()
        if format_lower not in EXPORT_FORMATS:
            return Response(
                content=json.dumps(
                    {
                        "error": f"Unknown format: {format}",
                        "valid_formats": list(EXPORT_FORMATS),
                    }
                ),
                media_type="application/json",
                status_code=400,
            )

        # Create appropriate exporter
        if format_lower == "json":
            exporter = JsonExporter(pretty=True)
            media_type = "application/json"
        elif format_lower == "markdown":
            exporter = MarkdownExporter()
            media_type = "text/markdown"
        elif format_lower == "sarif":
            exporter = SarifExporter()
            media_type = "application/json"
        elif format_lower == "agent":
            exporter = AgentExporter()
            media_type = "text/markdown"
        else:
            # Fallback (shouldn't reach here due to validation above)
            exporter = JsonExporter(pretty=True)
            media_type = "application/json"

        # Generate export content
        content = exporter.export(state.report)

        # Build filename with timestamp
        timestamp = state.report.generated_at.strftime("%Y%m%d_%H%M%S")
        filename = f"meilisearch-analysis_{timestamp}{exporter.file_extension}"

        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.get("/compare", response_class=HTMLResponse)
    async def compare_page(request: Request):
        """Render the comparison page for uploading two reports."""
        templates = request.app.state.templates

        return templates.TemplateResponse(
            "comparison.html",
            {
                "request": request,
                "comparison": None,
                "error": None,
            },
        )

    @app.post("/compare", response_class=HTMLResponse)
    async def compare_reports(
        request: Request,
        old_report_file: UploadFile = File(...),
        new_report_file: UploadFile = File(...),
    ):
        """Compare two uploaded JSON reports."""
        templates = request.app.state.templates
        error = None
        comparison = None

        try:
            # Parse old report
            old_content = await old_report_file.read()
            old_data = json.loads(old_content.decode("utf-8"))
            old_report = AnalysisReport.model_validate(old_data)

            # Parse new report
            new_content = await new_report_file.read()
            new_data = json.loads(new_content.decode("utf-8"))
            new_report = AnalysisReport.model_validate(new_data)

            # Run comparison
            analyzer = HistoricalAnalyzer()
            comparison = analyzer.compare(old_report, new_report)

        except json.JSONDecodeError as e:
            error = f"Invalid JSON in one of the uploaded files: {e}"
        except Exception as e:
            error = f"Error comparing reports: {e}"

        return templates.TemplateResponse(
            "comparison.html",
            {
                "request": request,
                "comparison": comparison,
                "error": error,
            },
        )

    @app.get("/api/compare")
    async def api_compare(
        request: Request,
        old_report_file: UploadFile = File(...),
        new_report_file: UploadFile = File(...),
    ) -> dict:
        """Compare two reports and return JSON result."""
        try:
            old_content = await old_report_file.read()
            old_data = json.loads(old_content.decode("utf-8"))
            old_report = AnalysisReport.model_validate(old_data)

            new_content = await new_report_file.read()
            new_data = json.loads(new_content.decode("utf-8"))
            new_report = AnalysisReport.model_validate(new_data)

            analyzer = HistoricalAnalyzer()
            comparison = analyzer.compare(old_report, new_report)

            return comparison.to_dict()

        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}"}
        except Exception as e:
            return {"error": str(e)}

    # ==================== Analysis Progress Routes ====================

    @app.get("/api/analysis/status")
    async def api_analysis_status(request: Request) -> dict:
        """Get current analysis status."""
        state: AppState = request.app.state.analyzer_state
        return {
            "status": state.analysis_status,
            "error": state.analysis_error,
            "has_report": state.report is not None,
        }

    @app.get("/api/analysis/events")
    async def api_analysis_events(request: Request):
        """Server-Sent Events endpoint for analysis progress.

        Streams progress events during analysis. Events are JSON objects with:
        - phase: "collect", "parse", or "analyze"
        - message: Human-readable status message
        - current: Current item number (optional)
        - total: Total items (optional)
        - index_uid: Index being processed (optional)

        A final event with data: null signals completion.
        """
        state: AppState = request.app.state.analyzer_state

        async def event_generator():
            """Generate SSE events from progress queue."""
            queue = state.subscribe_progress()
            try:
                # Send initial status
                yield {
                    "event": "status",
                    "data": json.dumps(
                        {
                            "status": state.analysis_status,
                            "error": state.analysis_error,
                        }
                    ),
                }

                # If analysis is not running, wait a bit for it to start
                # This handles the race condition where SSE connects before
                # the form submission triggers analysis
                if state.analysis_status != "running":
                    # Wait up to 5 seconds for analysis to start
                    for _ in range(50):
                        await asyncio.sleep(0.1)
                        if state.analysis_status == "running":
                            break

                    # If still not running, return current status
                    if state.analysis_status != "running":
                        yield {
                            "event": "done",
                            "data": json.dumps(
                                {
                                    "status": state.analysis_status,
                                    "has_report": state.report is not None,
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
                                        "status": state.analysis_status,
                                        "error": state.analysis_error,
                                        "has_report": state.report is not None,
                                    }
                                ),
                            }
                            break

                        # Send progress event
                        yield {
                            "event": "progress",
                            "data": json.dumps(event.to_dict()),
                        }

                    except asyncio.TimeoutError:
                        # Send heartbeat to keep connection alive
                        yield {"event": "heartbeat", "data": ""}

            finally:
                state.unsubscribe_progress(queue)

        return EventSourceResponse(event_generator())

    @app.post("/api/analyze")
    async def api_start_analysis(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> dict:
        """Start analysis in the background.

        Returns immediately with status. Use /api/analysis/events to track progress.
        """
        state: AppState = request.app.state.analyzer_state

        if state.analysis_status == "running":
            return {"status": "already_running"}

        if not state.meili_url and not state.dump_path:
            return {"status": "no_source", "error": "No data source configured"}

        # Close existing collector
        if state.collector:
            await state.collector.close()

        # Start analysis in background
        background_tasks.add_task(run_analysis, state)

        return {"status": "started"}

    @app.get("/api/tasks/summary")
    async def api_tasks_summary(request: Request) -> dict:
        """Get tasks summary statistics."""
        state: AppState = request.app.state.analyzer_state

        from meiliscan.collectors.live_instance import LiveInstanceCollector
        from meiliscan.models.task import Task, TasksSummary

        if state.meili_url:
            collector = LiveInstanceCollector(
                url=state.meili_url,
                api_key=state.meili_api_key,
            )
            try:
                if not await collector.connect():
                    return {"error": "Failed to connect to MeiliSearch instance"}

                summary = await collector.get_tasks_summary()
                return {
                    "total": summary.total,
                    "succeeded": summary.succeeded,
                    "failed": summary.failed,
                    "processing": summary.processing,
                    "enqueued": summary.enqueued,
                    "canceled": summary.canceled,
                    "success_rate": summary.success_rate,
                    "has_active": summary.has_active,
                }
            except Exception as e:
                return {"error": str(e)}
            finally:
                await collector.close()

        elif state.collector:
            try:
                raw_tasks = await state.collector.get_tasks(limit=1000)
                tasks = [Task(**t) for t in raw_tasks]
                summary = TasksSummary.from_tasks(tasks)
                return {
                    "total": summary.total,
                    "succeeded": summary.succeeded,
                    "failed": summary.failed,
                    "processing": summary.processing,
                    "enqueued": summary.enqueued,
                    "canceled": summary.canceled,
                    "success_rate": summary.success_rate,
                    "has_active": summary.has_active,
                }
            except Exception as e:
                return {"error": str(e)}

        return {"error": "No data source available"}
