"""Route definitions for the web dashboard."""

import asyncio
import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sse_starlette.sse import EventSourceResponse

from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.exporters.agent_exporter import AgentExporter
from meiliscan.exporters.json_exporter import JsonExporter
from meiliscan.exporters.markdown_exporter import MarkdownExporter
from meiliscan.exporters.sarif_exporter import SarifExporter
from meiliscan.models.report import AnalysisReport
from meiliscan.web.app import AppState, run_analysis

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

        from meiliscan.core.scorer import HealthScorer
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

        # Get health score breakdown if we have a report
        score_breakdown: dict | None = None
        if state.report:
            scorer = HealthScorer()
            all_findings = state.report.get_all_findings()
            score_breakdown = scorer.get_score_breakdown(all_findings)

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "report": state.report,
                "source_url": state.meili_url,
                "source_dump": state.dump_path,
                "tasks_summary": tasks_summary,
                "score_breakdown": score_breakdown,
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

    @app.post("/connect", response_class=HTMLResponse)
    async def connect_instance(
        request: Request,
        url: str = Form(...),
        api_key: str = Form(default=""),
        probe_search: str = Form(default=""),
        sample_documents: int = Form(default=20),
        sample_all: str = Form(default=""),
        detect_sensitive: str = Form(default=""),
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

        # Run new analysis
        await run_analysis(state)

        return RedirectResponse(url="/", status_code=303)

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_dump(
        request: Request,
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

        # Run new analysis
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

        return {
            "status": "ok",
            "health_score": state.report.summary.health_score,
            "total_indexes": state.report.summary.total_indexes,
            "total_documents": state.report.summary.total_documents,
            "critical_issues": state.report.summary.critical_issues,
            "warnings": state.report.summary.warnings,
        }

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

                # If analysis is not running, just return current status
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
