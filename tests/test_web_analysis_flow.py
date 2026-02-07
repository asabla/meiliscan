"""Tests for web analysis flow orchestration and locking behavior."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from meiliscan.web.app import AppState, create_app


@pytest.fixture
def app():
    """Create a test app without an initial source."""
    return create_app()


@pytest.fixture
def client(app) -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestAnalyzeApi:
    def test_api_analyze_no_source(self, client: TestClient):
        response = client.post("/api/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_source"
        assert "error" in data

    def test_api_analyze_already_running_when_locked(self, app, client: TestClient):
        state: AppState = app.state.analyzer_state
        asyncio.run(state.run_lock.acquire())
        try:
            response = client.post("/api/analyze")
            assert response.status_code == 200
            assert response.json()["status"] == "already_running"
        finally:
            state.run_lock.release()

    def test_api_analyze_uses_state_config_snapshot(
        self,
        app,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        state: AppState = app.state.analyzer_state
        state.meili_url = "http://localhost:7700"
        state.meili_api_key = "secret"
        state.sample_documents = 42
        captured: dict[str, Any] = {}

        async def fake_run_analysis(_state, emit_done: bool = True, config=None):
            captured["emit_done"] = emit_done
            captured["config"] = config

        monkeypatch.setattr(
            "meiliscan.web.routes_analysis.run_analysis",
            fake_run_analysis,
        )

        response = client.post("/api/analyze")

        assert response.status_code == 200
        assert response.json()["status"] == "started"
        assert captured["emit_done"] is True
        assert captured["config"] is not None
        assert captured["config"].meili_url == "http://localhost:7700"
        assert captured["config"].meili_api_key == "secret"
        assert captured["config"].sample_documents == 42


class TestConnectAndUpload:
    def test_connect_builds_config_for_background_run(
        self,
        app,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict[str, Any] = {}

        async def fake_run_analysis_and_benchmark(_state, config=None):
            captured["config"] = config

        monkeypatch.setattr(
            "meiliscan.web.routes_analysis.run_analysis_and_benchmark",
            fake_run_analysis_and_benchmark,
        )

        response = client.post(
            "/connect",
            headers={"accept": "application/json"},
            data={
                "url": "http://localhost:7700",
                "api_key": "master-key",
                "probe_search": "true",
                "sample_documents": "30",
                "sample_all": "",
                "detect_sensitive": "true",
                "run_benchmark": "true",
                "benchmark_mode": "comprehensive",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "started"
        config = captured["config"]
        assert config.meili_url == "http://localhost:7700"
        assert config.meili_api_key == "master-key"
        assert config.probe_search is True
        assert config.sample_documents == 30
        assert config.detect_sensitive is True
        assert config.run_benchmark is True
        assert config.comprehensive_benchmark is True

    def test_connect_rejects_when_run_lock_is_held(self, app, client: TestClient):
        state: AppState = app.state.analyzer_state
        asyncio.run(state.run_lock.acquire())
        try:
            response = client.post(
                "/connect",
                headers={"accept": "application/json"},
                data={"url": "http://localhost:7700"},
            )
            assert response.status_code == 409
            assert response.json()["status"] == "already_running"
        finally:
            state.run_lock.release()

    def test_upload_rejects_when_run_lock_is_held(self, app, client: TestClient):
        state: AppState = app.state.analyzer_state
        asyncio.run(state.run_lock.acquire())
        try:
            response = client.post(
                "/upload",
                headers={"accept": "application/json"},
                files={"file": ("sample.dump", b"dummy")},
                data={
                    "sample_documents": "20",
                    "sample_all": "",
                    "detect_sensitive": "",
                },
            )
            assert response.status_code == 409
            assert response.json()["status"] == "already_running"
        finally:
            state.run_lock.release()

    def test_upload_builds_dump_config_for_analysis(
        self,
        app,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict[str, Any] = {}

        async def fake_run_analysis(_state, emit_done: bool = True, config=None):
            captured["emit_done"] = emit_done
            captured["config"] = config

        monkeypatch.setattr(
            "meiliscan.web.routes_analysis.run_analysis",
            fake_run_analysis,
        )

        response = client.post(
            "/upload",
            headers={"accept": "application/json"},
            files={"file": ("sample.dump", b"dummy")},
            data={
                "sample_documents": "15",
                "sample_all": "true",
                "detect_sensitive": "true",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "started"
        config = captured["config"]
        assert config.dump_path is not None
        assert isinstance(config.dump_path, Path)
        assert config.sample_documents is None
        assert config.detect_sensitive is True
