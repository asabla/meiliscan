"""Route definitions for the web dashboard."""

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.exporters.agent_exporter import AgentExporter
from meiliscan.exporters.json_exporter import JsonExporter
from meiliscan.exporters.markdown_exporter import MarkdownExporter
from meiliscan.exporters.sarif_exporter import SarifExporter
from meiliscan.models.report import AnalysisReport
from meiliscan.web.app import AppState, run_analysis

# Valid export formats
EXPORT_FORMATS = ("json", "markdown", "sarif", "agent")


def register_routes(app: FastAPI) -> None:
    """Register all routes for the application."""

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Render the main dashboard."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "report": state.report,
                "source_url": state.meili_url,
                "source_dump": state.dump_path,
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

        # Get unique categories and indexes for filters
        categories = sorted(set(f.category.value for f in all_findings))
        indexes = sorted(set(f.index_uid for f in all_findings if f.index_uid))

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
    ):
        """Connect to a MeiliSearch instance."""
        state: AppState = request.app.state.analyzer_state

        # Update connection info
        state.meili_url = url
        state.meili_api_key = api_key if api_key else None
        state.dump_path = None

        # Close existing collector
        if state.collector:
            await state.collector.close()

        # Run new analysis
        await run_analysis(state)

        return RedirectResponse(url="/", status_code=303)

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_dump(request: Request, file: UploadFile = File(...)):
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

    @app.get("/api/indexes/{index_uid}/documents")
    async def api_index_documents(
        request: Request,
        index_uid: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict:
        """Get sample documents for an index.

        Args:
            index_uid: The index UID
            limit: Maximum number of documents to return (max 100)
            offset: Number of documents to skip

        Returns:
            Dictionary with documents and pagination info
        """
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return {"error": "No analysis data available"}

        if index_uid not in state.report.indexes:
            return {"error": f"Index '{index_uid}' not found"}

        index_analysis = state.report.indexes[index_uid]
        all_docs = index_analysis.sample_documents

        # Apply pagination
        limit = min(limit, 100)  # Cap at 100
        start = offset
        end = offset + limit

        paginated_docs = all_docs[start:end]

        return {
            "results": paginated_docs,
            "offset": offset,
            "limit": limit,
            "total": len(all_docs),
        }

    @app.get("/index/{index_uid}/documents", response_class=HTMLResponse)
    async def index_documents_partial(
        request: Request,
        index_uid: str,
        page: int = 1,
    ):
        """Render document samples partial (HTMX)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        documents = []
        total = 0
        per_page = 5

        if state.report and index_uid in state.report.indexes:
            index_analysis = state.report.indexes[index_uid]
            all_docs = index_analysis.sample_documents
            total = len(all_docs)

            start = (page - 1) * per_page
            end = start + per_page
            documents = all_docs[start:end]

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return templates.TemplateResponse(
            "components/document_samples.html",
            {
                "request": request,
                "index_uid": index_uid,
                "documents": documents,
                "page": page,
                "total_pages": total_pages,
                "total": total,
                "per_page": per_page,
            },
        )

    # ==================== Search Playground Routes ====================

    @app.get("/search", response_class=HTMLResponse)
    async def search_playground(request: Request, index: str | None = None):
        """Render the search playground page.

        Only available when connected to a live MeiliSearch instance.
        """
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        # Check if we're connected to a live instance
        if not state.meili_url:
            return templates.TemplateResponse(
                "search.html",
                {
                    "request": request,
                    "report": state.report,
                    "is_live": False,
                    "indexes": [],
                    "selected_index": None,
                    "index_settings": None,
                },
            )

        # Get list of indexes and their settings
        indexes = []
        index_settings = None

        if state.report:
            indexes = list(state.report.indexes.keys())

            # Get settings for selected index
            if index and index in state.report.indexes:
                index_settings = state.report.indexes[index].settings.get("current", {})
            elif indexes:
                # Default to first index
                index = indexes[0]
                index_settings = state.report.indexes[index].settings.get("current", {})

        return templates.TemplateResponse(
            "search.html",
            {
                "request": request,
                "report": state.report,
                "is_live": True,
                "indexes": indexes,
                "selected_index": index,
                "index_settings": index_settings,
            },
        )

    @app.get("/api/search/settings/{index_uid}")
    async def api_search_settings(request: Request, index_uid: str) -> dict:
        """Get index settings for the search form.

        Returns filterable attributes, sortable attributes, and distinct attribute.
        """
        state: AppState = request.app.state.analyzer_state

        if not state.report or index_uid not in state.report.indexes:
            return {"error": f"Index '{index_uid}' not found"}

        settings = state.report.indexes[index_uid].settings.get("current", {})

        return {
            "filterableAttributes": settings.get("filterableAttributes", []),
            "sortableAttributes": settings.get("sortableAttributes", []),
            "distinctAttribute": settings.get("distinctAttribute"),
            "searchableAttributes": settings.get("searchableAttributes", ["*"]),
        }

    @app.post("/api/search/{index_uid}")
    async def api_search(
        request: Request,
        index_uid: str,
    ) -> dict:
        """Execute a search query against a MeiliSearch index.

        Request body should contain:
        - q: Search query string
        - filter: Filter expression (optional)
        - sort: Array of sort expressions (optional)
        - distinct: Distinct attribute (optional)
        - hitsPerPage: Results per page (optional, default 20)
        - page: Page number (optional, default 1)
        """
        state: AppState = request.app.state.analyzer_state

        if not state.meili_url:
            return {"error": "Not connected to a live MeiliSearch instance"}

        # Parse request body
        try:
            body = await request.json()
        except Exception:
            body = {}

        query = body.get("q", "")
        filter_expr = body.get("filter") or None
        sort = body.get("sort") or None
        distinct = body.get("distinct") or None
        hits_per_page = body.get("hitsPerPage", 20)
        page = body.get("page", 1)

        # Get the live collector
        from meiliscan.collectors.live_instance import LiveInstanceCollector

        collector = LiveInstanceCollector(
            url=state.meili_url,
            api_key=state.meili_api_key,
        )

        try:
            if not await collector.connect():
                return {"error": "Failed to connect to MeiliSearch instance"}

            results = await collector.search(
                index_uid=index_uid,
                query=query,
                filter=filter_expr,
                sort=sort,
                distinct=distinct,
                hits_per_page=hits_per_page,
                page=page,
            )

            return results

        except Exception as e:
            return {"error": str(e)}
        finally:
            await collector.close()

    @app.post("/search/{index_uid}/results", response_class=HTMLResponse)
    async def search_results_partial(
        request: Request,
        index_uid: str,
    ):
        """Execute search and render results partial (HTMX)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        error = None
        results = None
        search_params = {}

        if not state.meili_url:
            error = "Not connected to a live MeiliSearch instance"
        else:
            # Parse form data
            form = await request.form()
            query = str(form.get("q", ""))
            filter_expr = str(form.get("filter", "")).strip() or None
            sort_field = str(form.get("sort_field", ""))
            sort_direction = str(form.get("sort_direction", "asc"))
            distinct = str(form.get("distinct", "")).strip() or None
            hits_per_page = int(str(form.get("hitsPerPage", "20")))
            page = int(str(form.get("page", "1")))

            # Build sort array if sort field is provided
            sort = None
            if sort_field:
                sort = [f"{sort_field}:{sort_direction}"]

            search_params = {
                "q": query,
                "filter": filter_expr,
                "sort": sort,
                "distinct": distinct,
                "hitsPerPage": hits_per_page,
                "page": page,
            }

            # Execute search
            from meiliscan.collectors.live_instance import LiveInstanceCollector

            collector = LiveInstanceCollector(
                url=state.meili_url,
                api_key=state.meili_api_key,
            )

            try:
                if not await collector.connect():
                    error = "Failed to connect to MeiliSearch instance"
                else:
                    results = await collector.search(
                        index_uid=index_uid,
                        query=query,
                        filter=filter_expr,
                        sort=sort,
                        distinct=distinct,
                        hits_per_page=hits_per_page,
                        page=page,
                    )
            except Exception as e:
                error = str(e)
            finally:
                await collector.close()

        return templates.TemplateResponse(
            "components/search_results.html",
            {
                "request": request,
                "index_uid": index_uid,
                "results": results,
                "error": error,
                "search_params": search_params,
            },
        )
