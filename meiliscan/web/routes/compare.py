"""Comparison route definitions."""

import json

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse

from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.models.report import AnalysisReport


def register_compare_routes(app: FastAPI) -> None:
    """Register comparison routes."""

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
