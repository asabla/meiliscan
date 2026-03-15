"""Connection management route definitions."""

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from meiliscan.web.app import (
    AppState,
    run_analysis,
    run_analysis_and_benchmark,
)


def register_connection_routes(app: FastAPI) -> None:
    """Register connection management routes."""

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

        # Update connection info
        state.meili_url = url
        state.meili_api_key = api_key if api_key else None
        state.dump_path = None

        # Update analysis options
        # HTML checkboxes submit their value only when checked, empty string otherwise
        state.probe_search = probe_search == "true"
        state.detect_sensitive = detect_sensitive == "true"
        state.run_benchmark = run_benchmark == "true"
        state.comprehensive_benchmark = benchmark_mode == "comprehensive"

        # Handle sample_all checkbox - if checked, set to None (all docs)
        if sample_all == "true":
            state.sample_documents = None
        else:
            state.sample_documents = max(
                1, min(sample_documents, 10000)
            )  # Validate range

        # Close existing collectors
        await state.close_live_collector()
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
        state.dump_filename = file.filename  # Preserve original filename
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

        # Close existing collectors
        await state.close_live_collector()
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

        # Close existing collectors
        await state.close_live_collector()
        if state.collector:
            await state.collector.close()

        # Reset all state
        state.report = None
        state.collector = None
        state.meili_url = None
        state.meili_api_key = None
        state.dump_path = None
        state.dump_filename = None

        return RedirectResponse(url="/", status_code=303)
