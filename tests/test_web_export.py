"""Tests for the web export endpoint."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from meiliscan.models.finding import Finding, FindingCategory, FindingSeverity
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
    finding = Finding(
        id="MEILI-S001",
        category=FindingCategory.SCHEMA,
        severity=FindingSeverity.CRITICAL,
        title="Test Finding",
        description="Test description",
        impact="Test impact",
        index_uid="test-index",
    )

    index_analysis = IndexAnalysis(
        metadata={"document_count": 100, "primary_key": "id"},
        settings={"current": {}},
        statistics={"field_count": 5},
        findings=[finding],
        sample_documents=[],
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
            warnings=0,
            suggestions=0,
            health_score=75,
        ),
        action_plan=ActionPlan(priority_order=["MEILI-S001"]),
    )


@pytest.fixture
def app_with_report(sample_report: AnalysisReport):
    """Create an app with a pre-populated report."""
    app = create_app()
    state: AppState = app.state.analyzer_state
    state.report = sample_report
    return app


@pytest.fixture
def client(app_with_report) -> TestClient:
    """Create a test client."""
    return TestClient(app_with_report)


class TestExportEndpoint:
    """Tests for /api/export endpoint."""

    def test_export_json(self, client: TestClient):
        """Test JSON export format."""
        response = client.get("/api/export?format=json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment" in response.headers["content-disposition"]
        assert ".json" in response.headers["content-disposition"]

        # Verify it's valid JSON
        data = response.json()
        assert "indexes" in data
        assert "summary" in data

    def test_export_markdown(self, client: TestClient):
        """Test Markdown export format."""
        response = client.get("/api/export?format=markdown")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "attachment" in response.headers["content-disposition"]
        assert ".md" in response.headers["content-disposition"]

        # Verify it contains markdown content
        content = response.text
        assert "# MeiliSearch Analysis Report" in content

    def test_export_sarif(self, client: TestClient):
        """Test SARIF export format."""
        response = client.get("/api/export?format=sarif")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment" in response.headers["content-disposition"]
        assert ".sarif" in response.headers["content-disposition"]

        # Verify it's valid SARIF JSON
        data = response.json()
        assert "$schema" in data
        assert "runs" in data

    def test_export_agent(self, client: TestClient):
        """Test Agent export format."""
        response = client.get("/api/export?format=agent")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "attachment" in response.headers["content-disposition"]
        assert ".md" in response.headers["content-disposition"]

        # Verify it contains agent-specific content
        content = response.text
        assert "MEILI-S001" in content

    def test_export_default_format(self, client: TestClient):
        """Test default export format (JSON)."""
        response = client.get("/api/export")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_export_invalid_format(self, client: TestClient):
        """Test invalid export format returns error."""
        response = client.get("/api/export?format=invalid")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "valid_formats" in data

    def test_export_case_insensitive(self, client: TestClient):
        """Test format parameter is case-insensitive."""
        response = client.get("/api/export?format=JSON")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_export_filename_has_timestamp(self, client: TestClient):
        """Test export filename includes timestamp."""
        response = client.get("/api/export?format=json")

        disposition = response.headers["content-disposition"]
        # Filename should include date from report: 20240101
        assert "meilisearch-analysis_" in disposition
        assert "20240101" in disposition


class TestTasksRoutes:
    """Smoke tests for tasks pages."""

    def test_tasks_page_exists(self):
        """Test /tasks returns an HTML page."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/tasks")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_tasks_list_exists(self):
        """Test /tasks/list returns an HTML fragment."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/tasks/list")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestExportWithoutReport:
    """Tests for export when no report is available."""

    def test_export_no_report(self):
        """Test export returns error when no report available."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/api/export?format=json")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "No analysis data available" in data["error"]
