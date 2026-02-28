"""API route definitions (report, health, statistics, export, analysis progress)."""

import asyncio
import json

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from meiliscan.exporters.agent_exporter import AgentExporter
from meiliscan.exporters.json_exporter import JsonExporter
from meiliscan.exporters.markdown_exporter import MarkdownExporter
from meiliscan.exporters.sarif_exporter import SarifExporter
from meiliscan.web.app import AppState, run_analysis
from meiliscan.web.routes._shared import EXPORT_FORMATS


def register_api_routes(app: FastAPI) -> None:
    """Register API routes."""

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

        from meiliscan.models.task import Task, TasksSummary

        if state.meili_url:
            collector = await state.get_live_collector()
            if not collector:
                return {"error": "Failed to connect to MeiliSearch instance"}

            try:
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
