"""Tests for web dashboard routes."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
)
from meiliscan.models.report import (
    ActionPlan,
    AnalysisReport,
    AnalysisSummary,
    IndexAnalysis,
    SourceInfo,
)
from meiliscan.web.app import AppState, create_app


@pytest.fixture
def sample_report() -> AnalysisReport:
    """Create a sample analysis report for testing."""
    critical_finding = Finding(
        id="MEILI-S001",
        category=FindingCategory.SCHEMA,
        severity=FindingSeverity.CRITICAL,
        title="Wildcard Searchable Attributes",
        description="Using wildcard for searchable attributes",
        impact="All fields are searched, degrading performance",
        index_uid="test-index",
        fix=FindingFix(
            type="settings_update",
            endpoint="/indexes/test-index/settings",
            payload={"searchableAttributes": ["title", "description"]},
        ),
    )

    warning_finding = Finding(
        id="MEILI-S005",
        category=FindingCategory.SCHEMA,
        severity=FindingSeverity.WARNING,
        title="ID Field in Searchable",
        description="Primary key field is in searchable attributes",
        impact="Unnecessary indexing of ID field",
        index_uid="test-index",
    )

    index_analysis = IndexAnalysis(
        metadata={"document_count": 100, "primary_key": "id"},
        settings={"current": {}},
        statistics={"field_count": 5},
        findings=[critical_finding, warning_finding],
        sample_documents=[{"id": 1, "title": "Test"}],
    )

    return AnalysisReport(
        generated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        source=SourceInfo(type="instance", url="http://localhost:7700"),
        version="1.0.0",
        indexes={"test-index": index_analysis},
        global_findings=[],
        summary=AnalysisSummary(
            total_indexes=1,
            total_documents=100,
            critical_issues=1,
            warnings=1,
            suggestions=0,
        ),
        action_plan=ActionPlan(priority_order=["MEILI-S001", "MEILI-S005"]),
    )


@pytest.fixture
def app_no_data():
    """Create an app with no data source."""
    return create_app()


@pytest.fixture
def app_with_report(sample_report: AnalysisReport):
    """Create an app with a pre-populated report."""
    app = create_app()
    state: AppState = app.state.analyzer_state
    state.report = sample_report
    return app


@pytest.fixture
def client_no_data(app_no_data) -> TestClient:
    """Test client with no data."""
    return TestClient(app_no_data)


@pytest.fixture
def client_with_report(app_with_report) -> TestClient:
    """Test client with pre-populated report."""
    return TestClient(app_with_report)


# ==================== Dashboard Tests ====================


class TestDashboard:
    """Tests for the main dashboard page."""

    def test_landing_page_no_data(self, client_no_data: TestClient):
        """Dashboard renders with connect form when no data."""
        response = client_no_data.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_dashboard_with_report(self, client_with_report: TestClient):
        """Dashboard renders report data when available."""
        response = client_with_report.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestIndexDetail:
    """Tests for index detail page."""

    def test_index_detail_exists(self, client_with_report: TestClient):
        """Index detail page renders for a known index."""
        response = client_with_report.get("/index/test-index")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_index_detail_unknown(self, client_with_report: TestClient):
        """Index detail page renders (with no data) for unknown index."""
        response = client_with_report.get("/index/nonexistent")
        assert response.status_code == 200


# ==================== Findings Tests ====================


class TestFindings:
    """Tests for the findings explorer page."""

    def test_findings_page(self, client_with_report: TestClient):
        """Findings page renders with findings."""
        response = client_with_report.get("/findings")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_findings_filter_severity(self, client_with_report: TestClient):
        """Findings page filters by severity."""
        response = client_with_report.get("/findings?severity=critical")
        assert response.status_code == 200

    def test_findings_filter_category(self, client_with_report: TestClient):
        """Findings page filters by category."""
        response = client_with_report.get("/findings?category=schema")
        assert response.status_code == 200

    def test_findings_list_partial(self, client_with_report: TestClient):
        """Findings list HTMX partial renders."""
        response = client_with_report.get("/findings/list")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_findings_list_filtered(self, client_with_report: TestClient):
        """Findings list HTMX partial filters work."""
        response = client_with_report.get("/findings/list?severity=warning")
        assert response.status_code == 200

    def test_finding_detail(self, client_with_report: TestClient):
        """Finding detail partial renders for known finding."""
        response = client_with_report.get("/finding/MEILI-S001")
        assert response.status_code == 200

    def test_finding_detail_unknown(self, client_with_report: TestClient):
        """Finding detail partial renders for unknown finding."""
        response = client_with_report.get("/finding/MEILI-UNKNOWN")
        assert response.status_code == 200

    def test_findings_page_no_data(self, client_no_data: TestClient):
        """Findings page renders with no report."""
        response = client_no_data.get("/findings")
        assert response.status_code == 200


# ==================== Tool Pages Tests ====================


class TestToolPages:
    """Tests for tool pages (search, tasks, documents)."""

    def test_search_page_no_live(self, client_with_report: TestClient):
        """Search page renders without live instance."""
        response = client_with_report.get("/search")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_tasks_page(self, client_with_report: TestClient):
        """Tasks page renders."""
        response = client_with_report.get("/tasks")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_tasks_list_partial(self, client_with_report: TestClient):
        """Tasks list HTMX partial renders."""
        response = client_with_report.get("/tasks/list")
        assert response.status_code == 200

    def test_documents_partial_dump(self, client_with_report: TestClient):
        """Documents partial uses cached samples from report."""
        response = client_with_report.get("/index/test-index/documents")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# ==================== API Tests ====================


class TestApiRoutes:
    """Tests for API endpoints."""

    def test_api_health_no_data(self, client_no_data: TestClient):
        """Health endpoint returns no_data status."""
        response = client_no_data.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_data"

    def test_api_health_with_report(self, client_with_report: TestClient):
        """Health endpoint returns ok status with report data."""
        response = client_with_report.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total_indexes"] == 1
        assert data["total_documents"] == 100
        assert data["critical_issues"] == 1

    def test_api_report_no_data(self, client_no_data: TestClient):
        """Report endpoint returns error when no data."""
        response = client_no_data.get("/api/report")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_api_report_with_data(self, client_with_report: TestClient):
        """Report endpoint returns full report."""
        response = client_with_report.get("/api/report")
        assert response.status_code == 200
        data = response.json()
        assert "indexes" in data
        assert "test-index" in data["indexes"]

    def test_api_statistics_no_data(self, client_no_data: TestClient):
        """Statistics endpoint returns error when no data."""
        response = client_no_data.get("/api/statistics")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_api_analysis_status_idle(self, client_no_data: TestClient):
        """Analysis status returns idle initially."""
        response = client_no_data.get("/api/analysis/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"
        assert data["has_report"] is False

    def test_api_analysis_status_with_report(self, client_with_report: TestClient):
        """Analysis status shows report available."""
        # Set status to done (normally set by run_analysis)
        app_state: AppState = client_with_report.app.state.analyzer_state
        app_state.analysis_status = "done"

        response = client_with_report.get("/api/analysis/status")
        data = response.json()
        assert data["status"] == "done"
        assert data["has_report"] is True


# ==================== Benchmark Safety Tests ====================


class TestBenchmarkSafety:
    """Tests for the fix benchmark safety gate."""

    def test_fix_apply_blocked_without_env(self, client_with_report: TestClient):
        """Fix benchmark with apply=True is blocked without env var."""
        import os

        # Ensure env var is not set
        os.environ.pop("MEILISCAN_ALLOW_APPLY_FIX", None)

        # Set up state for live instance
        state: AppState = client_with_report.app.state.analyzer_state
        state.meili_url = "http://localhost:7700"

        response = client_with_report.post(
            "/api/benchmark/fix/MEILI-S001?apply=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert "MEILISCAN_ALLOW_APPLY_FIX" in data["error"]

    def test_fix_dry_run_works(self, client_with_report: TestClient):
        """Fix benchmark dry run (apply=False) is not blocked."""
        # Without live instance, it should fail with "no live instance" error
        # but NOT with the safety gate error
        response = client_with_report.post(
            "/api/benchmark/fix/MEILI-S001?apply=false"
        )
        assert response.status_code == 200
        data = response.json()
        # Should get a different error (no live instance), not the safety gate
        assert "MEILISCAN_ALLOW_APPLY_FIX" not in data.get("error", "")

    def test_html_fix_apply_blocked(self, client_with_report: TestClient):
        """HTML fix benchmark endpoint also blocks apply=True."""
        import os

        os.environ.pop("MEILISCAN_ALLOW_APPLY_FIX", None)

        state: AppState = client_with_report.app.state.analyzer_state
        state.meili_url = "http://localhost:7700"

        response = client_with_report.post(
            "/benchmark/fix/MEILI-S001?apply=true"
        )
        assert response.status_code == 200
        assert "MEILISCAN_ALLOW_APPLY_FIX" in response.text


# ==================== Compare Page Tests ====================


class TestComparePage:
    """Tests for the comparison page."""

    def test_compare_page_renders(self, client_no_data: TestClient):
        """Compare page renders."""
        response = client_no_data.get("/compare")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_compare_page_with_report(self, client_with_report: TestClient):
        """Compare page renders with report available."""
        response = client_with_report.get("/compare")
        assert response.status_code == 200


# ==================== Benchmark Page Tests ====================


class TestBenchmarkPage:
    """Tests for the benchmark page."""

    def test_benchmark_page_no_live(self, client_with_report: TestClient):
        """Benchmark page renders without live instance."""
        response = client_with_report.get("/benchmark")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_benchmark_api_no_data(self, client_no_data: TestClient):
        """Benchmark API returns error when no data."""
        response = client_no_data.get("/api/benchmark")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_benchmark_api_no_results(self, client_with_report: TestClient):
        """Benchmark API returns no results when none exist."""
        response = client_with_report.get("/api/benchmark")
        assert response.status_code == 200
        data = response.json()
        assert data.get("available") is False


# ==================== Connection Flow Tests ====================


class TestConnectionFlow:
    """Tests for connection management."""

    def test_disconnect(self, client_with_report: TestClient):
        """Disconnect resets state and redirects."""
        response = client_with_report.post("/disconnect", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

        # State should be reset
        state: AppState = client_with_report.app.state.analyzer_state
        assert state.report is None
        assert state.meili_url is None

    def test_refresh_no_source(self, client_no_data: TestClient):
        """Refresh with no source still redirects."""
        response = client_no_data.post("/refresh", follow_redirects=False)
        assert response.status_code == 303
