"""Analysis lifecycle and status routes for the web dashboard."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from meiliscan.web.analysis_config import (
    AnalysisConfig,
    clamp_sample_documents,
    parse_checkbox,
)
from meiliscan.web.app import AppState, run_analysis, run_analysis_and_benchmark

logger = logging.getLogger(__name__)


def _build_live_analysis_config(
    *,
    state: AppState,
    url: str,
    api_key: str,
    probe_search: str,
    sample_documents: int,
    sample_all: str,
    detect_sensitive: str,
    run_benchmark: str,
    benchmark_mode: str,
) -> AnalysisConfig:
    """Build immutable analysis config from live-instance form inputs."""
    return AnalysisConfig(
        meili_url=url,
        meili_api_key=api_key if api_key else None,
        dump_path=None,
        probe_search=parse_checkbox(probe_search),
        sample_documents=clamp_sample_documents(sample_documents, sample_all),
        detect_sensitive=parse_checkbox(detect_sensitive),
        max_concurrent=state.max_concurrent,
        run_benchmark=parse_checkbox(run_benchmark),
        comprehensive_benchmark=benchmark_mode == "comprehensive",
    )


def _build_dump_analysis_config(
    *,
    state: AppState,
    dump_path: Path,
    sample_documents: int,
    sample_all: str,
    detect_sensitive: str,
) -> AnalysisConfig:
    """Build immutable analysis config from dump-upload form inputs."""
    return AnalysisConfig(
        meili_url=None,
        meili_api_key=None,
        dump_path=dump_path,
        probe_search=False,
        sample_documents=clamp_sample_documents(sample_documents, sample_all),
        detect_sensitive=parse_checkbox(detect_sensitive),
        max_concurrent=state.max_concurrent,
    )


def register_analysis_routes(app: FastAPI) -> None:
    """Register analysis lifecycle routes."""

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
        benchmark_mode: str = Form(default="basic"),
    ):
        """Connect to a MeiliSearch instance."""
        state: AppState = request.app.state.analyzer_state

        analysis_config = _build_live_analysis_config(
            state=state,
            url=url,
            api_key=api_key,
            probe_search=probe_search,
            sample_documents=sample_documents,
            sample_all=sample_all,
            detect_sensitive=detect_sensitive,
            run_benchmark=run_benchmark,
            benchmark_mode=benchmark_mode,
        )

        accept_header = request.headers.get("accept", "")
        is_ajax = "application/json" in accept_header

        if state.run_lock.locked():
            error = "Another analysis or benchmark is already running"
            if is_ajax:
                return JSONResponse(
                    {"status": "already_running", "error": error},
                    status_code=409,
                )
            state.analysis_error = error
            return RedirectResponse(url="/", status_code=303)

        if is_ajax:
            background_tasks.add_task(
                run_analysis_and_benchmark,
                state,
                analysis_config,
            )
            return JSONResponse({"status": "started"})

        await run_analysis_and_benchmark(state, analysis_config)
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

        with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        analysis_config = _build_dump_analysis_config(
            state=state,
            dump_path=tmp_path,
            sample_documents=sample_documents,
            sample_all=sample_all,
            detect_sensitive=detect_sensitive,
        )

        accept_header = request.headers.get("accept", "")
        is_ajax = "application/json" in accept_header

        if state.run_lock.locked():
            error = "Another analysis or benchmark is already running"
            if is_ajax:
                return JSONResponse(
                    {"status": "already_running", "error": error},
                    status_code=409,
                )
            state.analysis_error = error
            return RedirectResponse(url="/", status_code=303)

        if is_ajax:
            background_tasks.add_task(run_analysis, state, True, analysis_config)
            return JSONResponse({"status": "started"})

        await run_analysis(state, config=analysis_config)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/refresh", response_class=HTMLResponse)
    async def refresh_analysis(request: Request):
        """Re-run analysis with current source."""
        state: AppState = request.app.state.analyzer_state

        if state.run_lock.locked():
            state.analysis_error = "Another analysis or benchmark is already running"
            return RedirectResponse(url="/", status_code=303)

        await run_analysis(state, config=state.current_analysis_config())
        return RedirectResponse(url="/", status_code=303)

    @app.post("/disconnect", response_class=HTMLResponse)
    async def disconnect(request: Request):
        """Disconnect from current source and reset to initial state."""
        state: AppState = request.app.state.analyzer_state

        if state.run_lock.locked():
            state.analysis_error = "Cannot disconnect while analysis is running"
            return RedirectResponse(url="/", status_code=303)

        if state.collector:
            await state.collector.close()

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
        """Server-Sent Events endpoint for analysis progress."""
        state: AppState = request.app.state.analyzer_state

        async def event_generator():
            queue = state.subscribe_progress()
            try:
                yield {
                    "event": "status",
                    "data": json.dumps(
                        {
                            "status": state.analysis_status,
                            "error": state.analysis_error,
                        }
                    ),
                }

                if state.analysis_status != "running":
                    for _ in range(50):
                        await asyncio.sleep(0.1)
                        if state.analysis_status == "running":
                            break

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

                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)

                        if event is None:
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

                        yield {
                            "event": "progress",
                            "data": json.dumps(event.to_dict()),
                        }

                    except asyncio.TimeoutError:
                        yield {"event": "heartbeat", "data": ""}

            finally:
                state.unsubscribe_progress(queue)

        return EventSourceResponse(event_generator())

    @app.post("/api/analyze")
    async def api_start_analysis(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> dict:
        """Start analysis in the background."""
        state: AppState = request.app.state.analyzer_state

        if state.run_lock.locked():
            return {"status": "already_running"}

        config = state.current_analysis_config()
        if not config.has_source:
            return {"status": "no_source", "error": "No data source configured"}

        background_tasks.add_task(run_analysis, state, True, config)
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
            except (RuntimeError, ValueError, OSError) as exc:
                logger.exception("Failed to fetch live task summary")
                return {"error": str(exc)}
            finally:
                await collector.close()

        if state.collector:
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
            except (RuntimeError, ValueError, TypeError, ValidationError) as exc:
                logger.exception("Failed to build cached task summary")
                return {"error": str(exc)}

        return {"error": "No data source available"}
