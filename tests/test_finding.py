"""Tests for the Finding model."""

from datetime import datetime

import pytest

from meilisearch_analyzer.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
)


class TestFindingSeverity:
    """Tests for FindingSeverity enum."""

    def test_severity_values(self):
        """Test that all severity values are correct."""
        assert FindingSeverity.CRITICAL.value == "critical"
        assert FindingSeverity.WARNING.value == "warning"
        assert FindingSeverity.SUGGESTION.value == "suggestion"
        assert FindingSeverity.INFO.value == "info"


class TestFindingCategory:
    """Tests for FindingCategory enum."""

    def test_category_values(self):
        """Test that all category values are correct."""
        assert FindingCategory.SCHEMA.value == "schema"
        assert FindingCategory.DOCUMENTS.value == "documents"
        assert FindingCategory.PERFORMANCE.value == "performance"
        assert FindingCategory.BEST_PRACTICES.value == "best_practices"
        assert FindingCategory.SECURITY.value == "security"


class TestFindingFix:
    """Tests for FindingFix model."""

    def test_fix_creation(self):
        """Test creating a fix."""
        fix = FindingFix(
            type="settings_update",
            endpoint="PATCH /indexes/test/settings",
            payload={"searchableAttributes": ["title", "content"]},
        )
        assert fix.type == "settings_update"
        assert fix.endpoint == "PATCH /indexes/test/settings"
        assert fix.payload == {"searchableAttributes": ["title", "content"]}

    def test_fix_with_empty_payload(self):
        """Test creating a fix with empty payload."""
        fix = FindingFix(type="other", endpoint="/test")
        assert fix.payload == {}


class TestFinding:
    """Tests for Finding model."""

    def test_finding_creation(self):
        """Test creating a finding with all fields."""
        finding = Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Wildcard searchableAttributes",
            description="All fields are searchable",
            impact="Increased index size",
            index_uid="products",
            current_value=["*"],
            recommended_value=["title", "description"],
        )

        assert finding.id == "MEILI-S001"
        assert finding.category == FindingCategory.SCHEMA
        assert finding.severity == FindingSeverity.CRITICAL
        assert finding.title == "Wildcard searchableAttributes"
        assert finding.index_uid == "products"

    def test_finding_with_fix(self):
        """Test creating a finding with a fix."""
        fix = FindingFix(
            type="settings_update",
            endpoint="PATCH /indexes/test/settings",
            payload={"searchableAttributes": ["title"]},
        )
        finding = Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Test",
            description="Test description",
            impact="Test impact",
            fix=fix,
        )

        assert finding.fix is not None
        assert finding.fix.type == "settings_update"

    def test_finding_to_dict(self):
        """Test converting finding to dictionary."""
        finding = Finding(
            id="MEILI-S001",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.CRITICAL,
            title="Test",
            description="Test description",
            impact="Test impact",
            index_uid="test",
            references=["https://example.com"],
        )

        data = finding.to_dict()
        assert data["id"] == "MEILI-S001"
        assert data["category"] == "schema"
        assert data["severity"] == "critical"
        assert data["index_uid"] == "test"
        assert "references" in data

    def test_finding_without_optional_fields(self):
        """Test finding without optional fields."""
        finding = Finding(
            id="MEILI-TEST",
            category=FindingCategory.PERFORMANCE,
            severity=FindingSeverity.INFO,
            title="Test",
            description="Test description",
            impact="None",
        )

        assert finding.index_uid is None
        assert finding.current_value is None
        assert finding.recommended_value is None
        assert finding.fix is None
        assert finding.references == []

    def test_finding_detected_at_auto_generated(self):
        """Test that detected_at is automatically set."""
        finding = Finding(
            id="MEILI-TEST",
            category=FindingCategory.SCHEMA,
            severity=FindingSeverity.INFO,
            title="Test",
            description="Test",
            impact="Test",
        )

        assert finding.detected_at is not None
        assert isinstance(finding.detected_at, datetime)
