"""Search, tasks, and document browsing route definitions."""

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from meiliscan.web.app import AppState


def register_tools_routes(app: FastAPI) -> None:
    """Register search, tasks, and document browsing routes."""

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
            collector = await state.get_live_collector()
            if collector:
                try:
                    offset = (page - 1) * per_page
                    data = await collector.get_documents(
                        index_uid=index_uid,
                        limit=per_page,
                        offset=offset,
                    )
                    documents = data.get("results", [])
                    total = data.get("total", len(documents))
                except Exception as e:
                    error = str(e)
            else:
                error = "Failed to connect to MeiliSearch instance"
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
            collector = await state.get_live_collector()
            if collector:
                try:
                    # Use lightweight method - only fetches UIDs, not full index data
                    indexes = await collector.list_index_uids()

                    selected_index = index or (indexes[0] if indexes else None)
                    if selected_index:
                        # Fetch settings only for the selected index
                        index_settings = await collector.get_index_settings(
                            selected_index
                        )
                except Exception:
                    pass  # Render page without data on connection error

        return templates.TemplateResponse(
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
            collector = await state.get_live_collector()
            if collector:
                try:
                    index_settings = await collector.get_index_settings(index_uid)
                except Exception:
                    pass

        return templates.TemplateResponse(
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
                "components/search_results.html",
                {
                    "request": request,
                    "error": "Live connection required for search",
                    "results": None,
                    "search_params": {},
                },
            )

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

        collector = await state.get_live_collector()
        if not collector:
            return templates.TemplateResponse(
                "components/search_results.html",
                {
                    "request": request,
                    "error": "Failed to connect to MeiliSearch instance",
                    "results": None,
                    "search_params": {},
                },
            )

        try:
            results = await collector.search(
                index_uid=index_uid,
                query=q,
                filter=filter_expr,
                sort=sort,
                page=page_num,
                hits_per_page=hits_per_page,
                distinct=distinct_attr,
            )
        except Exception as e:
            error = str(e)

        return templates.TemplateResponse(
            "components/search_results.html",
            {
                "request": request,
                "error": error,
                "results": results,
                "search_params": search_params,
            },
        )

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
            except Exception as e:
                error = str(e)

        return templates.TemplateResponse(
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
        except Exception as e:
            return templates.TemplateResponse(
                "components/tasks_list.html",
                {
                    "request": request,
                    "tasks": [],
                    "error": str(e),
                    "next_uid": None,
                    "current_status": status,
                    "current_type": task_type,
                    "current_index": index,
                },
            )
