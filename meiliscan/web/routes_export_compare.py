"""Export and comparison routes for the web dashboard."""

import json

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError

from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.exporters.agent_exporter import AgentExporter
from meiliscan.exporters.json_exporter import JsonExporter
from meiliscan.exporters.markdown_exporter import MarkdownExporter
from meiliscan.exporters.sarif_exporter import SarifExporter
from meiliscan.models.report import AnalysisReport
from meiliscan.web.app import AppState
from meiliscan.web.routes_common import EXPORT_FORMATS


def register_export_compare_routes(app: FastAPI) -> None:
    """Register report export and historical comparison routes."""

    @app.get("/api/export")
    async def api_export(request: Request, format: str = "json") -> Response:
        """Export the analysis report in various formats."""
        state: AppState = request.app.state.analyzer_state

        if not state.report:
            return Response(
                content=json.dumps({"error": "No analysis data available"}),
                media_type="application/json",
                status_code=400,
            )

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
            exporter = JsonExporter(pretty=True)
            media_type = "application/json"

        content = exporter.export(state.report)
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
            request,
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
            old_content = await old_report_file.read()
            old_data = json.loads(old_content.decode("utf-8"))
            old_report = AnalysisReport.model_validate(old_data)

            new_content = await new_report_file.read()
            new_data = json.loads(new_content.decode("utf-8"))
            new_report = AnalysisReport.model_validate(new_data)

            analyzer = HistoricalAnalyzer()
            comparison = analyzer.compare(old_report, new_report)

        except json.JSONDecodeError as exc:
            error = f"Invalid JSON in one of the uploaded files: {exc}"
        except (ValidationError, ValueError) as exc:
            error = f"Error comparing reports: {exc}"

        return templates.TemplateResponse(
            request,
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

        except json.JSONDecodeError as exc:
            return {"error": f"Invalid JSON: {exc}"}
        except (ValidationError, ValueError) as exc:
            return {"error": str(exc)}
