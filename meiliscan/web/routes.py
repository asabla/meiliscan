"""Route definitions for index/findings/search dashboard pages."""

import logging

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from meiliscan.web.app import AppState
from meiliscan.web.routes_analysis import register_analysis_routes
from meiliscan.web.routes_benchmark import register_benchmark_routes
from meiliscan.web.routes_common import sort_findings_by_severity
from meiliscan.web.routes_export_compare import register_export_compare_routes
from meiliscan.web.routes_tasks import register_tasks_routes

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    """Register all routes for the application."""
    register_analysis_routes(app)
    register_benchmark_routes(app)
    register_tasks_routes(app)
    register_export_compare_routes(app)

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
            except (RuntimeError, ValueError, TypeError, ValidationError):
                logger.exception("Failed to build dashboard task summary")

        return templates.TemplateResponse(
            request,
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
            request,
            "index_detail.html",
            {
                "request": request,
                "report": state.report,
                "index_uid": index_uid,
                "index_analysis": index_analysis,
            },
        )

    @app.get("/index/{index_uid}/documents", response_class=HTMLResponse)
    async def index_documents_partial(
        request: Request,
        index_uid: str,
        page: int = 1,
        per_page: int = 10,
    ):
        """Fetch paginated documents for an index (HTMX partial)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        documents: list = []
        total = 0
        error: str | None = None

        # Fetch from live instance if available
        if state.meili_url:
            from meiliscan.collectors.live_instance import LiveInstanceCollector

            collector = LiveInstanceCollector(
                url=state.meili_url,
                api_key=state.meili_api_key,
            )
            try:
                if await collector.connect():
                    offset = (page - 1) * per_page
                    data = await collector.get_documents(
                        index_uid=index_uid,
                        limit=per_page,
                        offset=offset,
                    )
                    documents = data.get("results", [])
                    total = data.get("total", len(documents))
                else:
                    error = "Failed to connect to MeiliSearch instance"
            except (RuntimeError, ValueError, OSError) as exc:
                error = str(exc)
                logger.exception("Failed loading index documents")
            finally:
                await collector.close()
        elif state.report and index_uid in state.report.indexes:
            # Use cached sample documents from dump analysis
            index_analysis = state.report.indexes[index_uid]
            all_docs = index_analysis.sample_documents or []
            total = len(all_docs)
            start = (page - 1) * per_page
            end = start + per_page
            documents = all_docs[start:end]
        else:
            error = "No data source available"

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return templates.TemplateResponse(
            request,
            "components/document_samples.html",
            {
                "request": request,
                "documents": documents,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "index_uid": index_uid,
                "error": error,
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
            request,
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
            request,
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
            request,
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
            request,
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
            request,
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
                request,
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
                request,
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
        except (RuntimeError, ValueError, OSError) as exc:
            error = str(exc)
            logger.exception("Search request failed")
        finally:
            await collector.close()

        return templates.TemplateResponse(
            request,
            "components/search_results.html",
            {
                "request": request,
                "error": error,
                "results": results,
                "search_params": search_params,
            },
        )
