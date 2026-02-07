"""Task queue routes for the web dashboard."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from meiliscan.web.app import AppState

logger = logging.getLogger(__name__)


def register_tasks_routes(app: FastAPI) -> None:
    """Register task queue routes."""

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(
        request: Request,
        status: str | None = None,
        task_type: str | None = None,
        index: str | None = None,
    ):
        """Render tasks queue page."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        from meiliscan.models.task import Task, TasksSummary

        error: str | None = None
        tasks_summary: TasksSummary | None = None
        indexes: list[str] = []

        if not state.meili_url and not state.collector:
            error = "No data source configured"
        else:
            try:
                raw_tasks = []
                if state.collector:
                    raw_tasks = await state.collector.get_tasks(limit=1000)
                tasks = [Task(**t) for t in raw_tasks]
                tasks_summary = TasksSummary.from_tasks(tasks)
                indexes = sorted({t.index_uid for t in tasks if t.index_uid})
            except (RuntimeError, ValueError, TypeError, ValidationError) as exc:
                error = str(exc)
                logger.exception("Failed to load tasks page data")

        return templates.TemplateResponse(
            request,
            "tasks.html",
            {
                "request": request,
                "is_live": bool(state.meili_url),
                "error": error,
                "summary": tasks_summary,
                "indexes": indexes,
                "current_status": status,
                "current_type": task_type,
                "current_index": index,
            },
        )

    @app.get("/tasks/list", response_class=HTMLResponse)
    async def tasks_list_partial(
        request: Request,
        status: str | None = None,
        task_type: str | None = None,
        index: str | None = None,
        from_uid: int | None = None,
        limit: int = 100,
    ):
        """Render tasks table partial (HTMX)."""
        state: AppState = request.app.state.analyzer_state
        templates = request.app.state.templates

        from meiliscan.models.task import Task

        if not state.collector:
            return templates.TemplateResponse(
                request,
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": [],
                    "error": "No tasks available (no collector)",
                    "next_uid": None,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )

        try:
            raw_tasks = await state.collector.get_tasks(limit=1000)
            tasks = [Task(**t) for t in raw_tasks]

            filtered = tasks
            if status:
                filtered = [t for t in filtered if t.status.value == status]
            if task_type:
                filtered = [t for t in filtered if t.task_type == task_type]
            if index:
                filtered = [t for t in filtered if t.index_uid == index]

            filtered.sort(key=lambda t: t.uid, reverse=True)

            if from_uid is not None:
                filtered = [t for t in filtered if t.uid < from_uid]

            page = filtered[:limit]
            next_uid_val = page[-1].uid if len(page) == limit else None

            return templates.TemplateResponse(
                request,
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": page,
                    "error": None,
                    "next_uid": next_uid_val,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )
        except (RuntimeError, ValueError, TypeError, ValidationError) as exc:
            return templates.TemplateResponse(
                request,
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": [],
                    "error": str(exc),
                    "next_uid": None,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )
