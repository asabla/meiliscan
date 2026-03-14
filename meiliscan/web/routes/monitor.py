"""Monitoring routes for live instance tracking."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import StreamingResponse


def register_monitor_routes(app: FastAPI) -> None:
    """Register monitoring routes."""

    @app.get("/monitor", response_class=HTMLResponse)
    async def monitor_page(request: Request):
        """Monitoring dashboard page."""
        state = request.app.state.analyzer_state
        templates = request.app.state.templates

        return templates.TemplateResponse(
            "monitor.html",
            {
                "request": request,
                "monitoring_enabled": state.monitoring_enabled,
                "monitoring_interval": state.monitoring_interval,
                "history": [s.to_event_dict() for s in state.monitoring_history[-100:]],
                "is_live": state.meili_url is not None,
                "source_url": state.meili_url,
            },
        )

    @app.post("/api/monitor/start")
    async def start_monitoring(request: Request):
        """Start the monitoring background loop."""
        state = request.app.state.analyzer_state

        if not state.meili_url:
            return JSONResponse(
                {"error": "Not connected to a live instance"}, status_code=400
            )

        # Parse optional interval from body
        try:
            body = await request.json()
            interval = body.get("interval", state.monitoring_interval)
            state.monitoring_interval = max(5, min(300, int(interval)))
        except Exception:
            pass

        await state.start_monitoring()
        return JSONResponse({"status": "started", "interval": state.monitoring_interval})

    @app.post("/api/monitor/stop")
    async def stop_monitoring(request: Request):
        """Stop the monitoring background loop."""
        state = request.app.state.analyzer_state
        await state.stop_monitoring()
        return JSONResponse({"status": "stopped"})

    @app.get("/api/monitor/events")
    async def monitor_events(request: Request):
        """Server-Sent Events stream for monitoring snapshots."""
        state = request.app.state.analyzer_state
        queue = state.subscribe_monitoring()

        async def event_generator():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30)
                        if event is None:
                            yield f"event: stopped\ndata: {{}}\n\n"
                            break
                        yield f"event: snapshot\ndata: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        yield f"event: heartbeat\ndata: {{}}\n\n"
            finally:
                state.unsubscribe_monitoring(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/monitor/history")
    async def monitor_history(request: Request):
        """Get monitoring history."""
        state = request.app.state.analyzer_state
        limit = int(request.query_params.get("limit", "100"))
        snapshots = state.monitoring_history[-limit:]
        return JSONResponse([s.to_event_dict() for s in snapshots])
