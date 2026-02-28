"""Dashboard and findings route definitions."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from meiliscan.web.app import AppState
from meiliscan.web.routes._shared import sort_findings_by_severity


def register_dashboard_routes(app: FastAPI) -> None:
    """Register dashboard and findings routes."""

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

        # Get unique categories and indexes for filter dropdowns
        categories = sorted({f.category.value for f in all_findings})
        indexes = sorted({f.index_uid for f in all_findings if f.index_uid})

        # Count by severity
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
