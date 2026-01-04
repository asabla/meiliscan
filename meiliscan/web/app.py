"""FastAPI application for the web dashboard."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meiliscan.core.collector import DataCollector
from meiliscan.core.reporter import Reporter
from meiliscan.models.report import AnalysisReport


class AppState:
    """Application state container."""

    def __init__(self):
        self.report: AnalysisReport | None = None
        self.collector: DataCollector | None = None
        self.meili_url: str | None = None
        self.meili_api_key: str | None = None
        self.dump_path: Path | None = None
        # Analysis options
        self.probe_search: bool = False
        self.sample_documents: int = 20
        self.detect_sensitive: bool = False


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


# Severity order for sorting (lower number = higher priority)
SEVERITY_ORDER = {
    "critical": 0,
    "warning": 1,
    "suggestion": 2,
    "info": 3,
}


def sort_by_severity(findings: list) -> list:
    """Sort findings by severity (critical first, then warning, suggestion, info)."""
    return sorted(
        findings,
        key=lambda f: SEVERITY_ORDER.get(
            f.severity.value.lower()
            if hasattr(f.severity, "value")
            else str(f.severity).lower(),
            4,
        ),
    )


def create_app(
    meili_url: str | None = None,
    meili_api_key: str | None = None,
    dump_path: Path | None = None,
    probe_search: bool = False,
    sample_documents: int = 20,
    detect_sensitive: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        meili_url: MeiliSearch instance URL
        meili_api_key: MeiliSearch API key
        dump_path: Path to dump file for offline analysis
        probe_search: Run read-only search probes to validate sort/filter configuration
        sample_documents: Number of sample documents to fetch per index
        detect_sensitive: Enable detection of potential PII/sensitive fields

    Returns:
        Configured FastAPI application
    """
    state = AppState()
    state.meili_url = meili_url
    state.meili_api_key = meili_api_key
    state.dump_path = dump_path
    state.probe_search = probe_search
    state.sample_documents = sample_documents
    state.detect_sensitive = detect_sensitive

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
        title="Meiliscan",
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
    templates.env.filters["sort_by_severity"] = sort_by_severity

    # Add global template function to check if connected to live instance
    def is_live_instance() -> bool:
        return state.meili_url is not None

    templates.env.globals["is_live_instance"] = is_live_instance

    # Store state and templates in app
    app.state.analyzer_state = state
    app.state.templates = templates

    # Register routes
    from meiliscan.web.routes import register_routes

    register_routes(app)

    return app


async def run_analysis(state: AppState) -> None:
    """Run analysis and store results in state.

    Uses the analysis options stored in state:
    - sample_documents: Number of sample documents to fetch per index
    - probe_search: Run search probes (live instance only)
    - detect_sensitive: Enable PII/sensitive field detection
    """
    try:
        if state.dump_path:
            state.collector = DataCollector.from_dump(
                state.dump_path,
                max_sample_docs=state.sample_documents,
            )
        elif state.meili_url:
            state.collector = DataCollector.from_url(
                state.meili_url,
                api_key=state.meili_api_key,
                sample_docs=state.sample_documents,
            )
        else:
            return

        # Collect data
        if not await state.collector.collect():
            print("Failed to collect data from source")
            return

        # Build analysis options
        analysis_options: dict = {
            "detect_sensitive": state.detect_sensitive,
            "sample_documents": state.sample_documents,
        }

        # Run search probes if requested (live instance only)
        if state.probe_search and state.meili_url:
            from meiliscan.analyzers.search_probe_analyzer import SearchProbeAnalyzer
            from meiliscan.collectors.live_instance import LiveInstanceCollector

            probe_analyzer = SearchProbeAnalyzer()

            # Access the underlying LiveInstanceCollector for search
            live_collector = state.collector._collector
            if isinstance(live_collector, LiveInstanceCollector):

                async def search_fn(index_uid, query, filter, sort):
                    return await live_collector.search(
                        index_uid=index_uid,
                        query=query,
                        filter=filter,
                        sort=sort,
                    )

                probe_findings, _ = await probe_analyzer.analyze(
                    state.collector.indexes, search_fn
                )
                analysis_options["_probe_findings"] = probe_findings

        # Run analysis
        reporter = Reporter(state.collector, analysis_options=analysis_options)
        state.report = reporter.generate_report(source_url=state.meili_url)
    except Exception as e:
        # Log error but don't crash - UI will show "no data" state
        print(f"Error running analysis: {e}")
