"""FastAPI application for the web dashboard."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meilisearch_analyzer.core.analyzer import Analyzer
from meilisearch_analyzer.core.collector import DataCollector
from meilisearch_analyzer.core.reporter import Reporter
from meilisearch_analyzer.core.scorer import HealthScorer
from meilisearch_analyzer.models.report import AnalysisReport


class AppState:
    """Application state container."""

    def __init__(self):
        self.report: AnalysisReport | None = None
        self.collector: DataCollector | None = None
        self.meili_url: str | None = None
        self.meili_api_key: str | None = None
        self.dump_path: Path | None = None


# Template filters - defined before create_app so they're available at registration time


def severity_color(severity: str) -> str:
    """Get CSS color class for severity level."""
    colors = {
        "critical": "red",
        "warning": "yellow",
        "suggestion": "blue",
        "info": "gray",
    }
    return colors.get(severity.lower(), "gray")


def severity_icon(severity: str) -> str:
    """Get icon for severity level."""
    icons = {
        "critical": "🔴",
        "warning": "🟡",
        "suggestion": "🔵",
        "info": "⚪",
    }
    return icons.get(severity.lower(), "⚪")


def format_number(value: int | float) -> str:
    """Format number with thousands separators."""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def trend_icon(trend: str) -> str:
    """Get icon for trend direction."""
    icons = {
        "up": "&#8593;",
        "down": "&#8595;",
        "stable": "&#8596;",
    }
    trend_str = trend.lower() if hasattr(trend, "lower") else str(trend)
    return icons.get(trend_str, "&#8596;")


def trend_color(trend: str) -> str:
    """Get CSS color class for trend direction."""
    colors = {
        "up": "green",
        "down": "red",
        "stable": "blue",
    }
    trend_str = trend.lower() if hasattr(trend, "lower") else str(trend)
    return colors.get(trend_str, "gray")


def create_app(
    meili_url: str | None = None,
    meili_api_key: str | None = None,
    dump_path: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        meili_url: MeiliSearch instance URL
        meili_api_key: MeiliSearch API key
        dump_path: Path to dump file for offline analysis

    Returns:
        Configured FastAPI application
    """
    state = AppState()
    state.meili_url = meili_url
    state.meili_api_key = meili_api_key
    state.dump_path = dump_path

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan manager."""
        # Startup: Run initial analysis if source provided
        if state.meili_url or state.dump_path:
            await run_analysis(state)
        yield
        # Shutdown: Clean up collector
        if state.collector:
            await state.collector.close()

    app = FastAPI(
        title="MeiliSearch Analyzer",
        description="Analyze MeiliSearch instances and dumps for optimization opportunities",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount static files
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Set up templates
    templates_path = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=templates_path)

    # Add custom template filters
    templates.env.filters["severity_color"] = severity_color
    templates.env.filters["severity_icon"] = severity_icon
    templates.env.filters["format_number"] = format_number
    templates.env.filters["trend_icon"] = trend_icon
    templates.env.filters["trend_color"] = trend_color

    # Store state and templates in app
    app.state.analyzer_state = state
    app.state.templates = templates

    # Register routes
    from meilisearch_analyzer.web.routes import register_routes

    register_routes(app)

    return app


async def run_analysis(state: AppState) -> None:
    """Run analysis and store results in state."""
    try:
        if state.dump_path:
            state.collector = DataCollector.from_dump(state.dump_path)
        elif state.meili_url:
            state.collector = DataCollector.from_url(
                state.meili_url,
                api_key=state.meili_api_key,
            )
        else:
            return

        # Collect data
        if not await state.collector.collect():
            print("Failed to collect data from source")
            return

        # Run analysis
        reporter = Reporter(state.collector)
        state.report = reporter.generate_report(source_url=state.meili_url)
    except Exception as e:
        # Log error but don't crash - UI will show "no data" state
        print(f"Error running analysis: {e}")
