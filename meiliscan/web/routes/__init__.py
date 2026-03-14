"""Web dashboard route modules."""

from fastapi import FastAPI

from meiliscan.web.routes.api import register_api_routes
from meiliscan.web.routes.benchmark import register_benchmark_routes
from meiliscan.web.routes.compare import register_compare_routes
from meiliscan.web.routes.connection import register_connection_routes
from meiliscan.web.routes.dashboard import register_dashboard_routes
from meiliscan.web.routes.monitor import register_monitor_routes
from meiliscan.web.routes.tools import register_tools_routes


def register_routes(app: FastAPI) -> None:
    """Register all routes for the application."""
    register_dashboard_routes(app)
    register_tools_routes(app)
    register_benchmark_routes(app)
    register_connection_routes(app)
    register_api_routes(app)
    register_compare_routes(app)
    register_monitor_routes(app)
