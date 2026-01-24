"""Report models for analysis output."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from meiliscan.models.benchmark import BenchmarkReport
from meiliscan.models.finding import Finding
from meiliscan.models.index import IndexData
from meiliscan.models.statistics import InstanceStatistics


class SourceInfo(BaseModel):
    """Information about the analysis source."""

    type: Literal["instance", "dump"] = Field(..., description="Source type")
    url: str | None = Field(default=None, description="MeiliSearch instance URL")
    meilisearch_version: str | None = Field(
        default=None, description="MeiliSearch version"
    )
    dump_path: str | None = Field(default=None, description="Path to dump file")
    dump_date: datetime | None = Field(default=None, description="Dump creation date")


class AnalysisSummary(BaseModel):
    """Summary of the analysis results."""

    total_indexes: int = Field(default=0, description="Total number of indexes")
    total_documents: int = Field(default=0, description="Total document count")
    database_size_bytes: int | None = Field(
        default=None, description="Database size in bytes"
    )
    critical_issues: int = Field(default=0, description="Number of critical issues")
    warnings: int = Field(default=0, description="Number of warnings")
    suggestions: int = Field(default=0, description="Number of suggestions")
    info_count: int = Field(default=0, description="Number of info items")


class IndexAnalysis(BaseModel):
    """Analysis results for a single index."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    statistics: dict[str, Any] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    sample_documents: list[dict[str, Any]] = Field(default_factory=list)


class ActionPlan(BaseModel):
    """Recommended action plan based on findings."""

    priority_order: list[str] = Field(
        default_factory=list, description="Finding IDs in priority order"
    )
    estimated_impact: dict[str, str] = Field(
        default_factory=dict, description="Estimated improvements"
    )


class AnalysisReport(BaseModel):
    """Complete analysis report."""

    schema_version: str = Field(default="1.1.0", alias="$schema_version")
    version: str = Field(default="1.1.0", description="Report format version")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    source: SourceInfo = Field(..., description="Source information")
    summary: AnalysisSummary = Field(default_factory=AnalysisSummary)
    indexes: dict[str, IndexAnalysis] = Field(default_factory=dict)
    global_findings: list[Finding] = Field(default_factory=list)
    action_plan: ActionPlan = Field(default_factory=ActionPlan)

    # Statistics (replaces health_score)
    statistics: InstanceStatistics | None = Field(
        default=None, description="Instance statistics and performance metrics"
    )

    # Benchmark results (optional, only for live instances)
    benchmark: BenchmarkReport | None = Field(
        default=None, description="Benchmark results (live instances only)"
    )

    # Internal storage not exported
    _raw_indexes: dict[str, IndexData] = {}
    _findings_cache: list[Finding] | None = None
    _finding_count: int = 0

    model_config = {"populate_by_name": True}

    def _invalidate_cache(self) -> None:
        """Invalidate the findings cache."""
        self._findings_cache = None

    def add_index(self, index: IndexData) -> None:
        """Add an index to the report."""
        self._raw_indexes[index.uid] = index
        self.indexes[index.uid] = IndexAnalysis(
            metadata={
                "primary_key": index.primary_key,
                "created_at": index.created_at.isoformat()
                if index.created_at
                else None,
                "updated_at": index.updated_at.isoformat()
                if index.updated_at
                else None,
                "document_count": index.document_count,
            },
            settings={
                "current": index.settings.model_dump(by_alias=True, exclude_none=True),
            },
            statistics={
                "field_distribution": index.stats.field_distribution,
                "field_count": index.field_count,
                "is_indexing": index.stats.is_indexing,
            },
            sample_documents=index.sample_documents,
        )

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to the appropriate location in the report."""
        self._invalidate_cache()
        self._finding_count += 1
        if finding.index_uid and finding.index_uid in self.indexes:
            self.indexes[finding.index_uid].findings.append(finding)
        else:
            self.global_findings.append(finding)

    @property
    def finding_count(self) -> int:
        """Get the total number of findings without building the list."""
        return self._finding_count

    def calculate_summary(self) -> None:
        """Calculate summary statistics from findings."""
        all_findings = self.get_all_findings()

        self.summary.total_indexes = len(self.indexes)
        self.summary.total_documents = sum(
            idx.metadata.get("document_count", 0) for idx in self.indexes.values()
        )
        self.summary.critical_issues = sum(
            1 for f in all_findings if f.severity.value == "critical"
        )
        self.summary.warnings = sum(
            1 for f in all_findings if f.severity.value == "warning"
        )
        self.summary.suggestions = sum(
            1 for f in all_findings if f.severity.value == "suggestion"
        )
        self.summary.info_count = sum(
            1 for f in all_findings if f.severity.value == "info"
        )

    def get_all_findings(self) -> list[Finding]:
        """Get all findings from the report (cached)."""
        if self._findings_cache is not None:
            return self._findings_cache

        findings: list[Finding] = list(self.global_findings)
        for index_analysis in self.indexes.values():
            findings.extend(index_analysis.findings)

        self._findings_cache = findings
        return findings

    def get_finding_by_id(self, finding_id: str) -> Finding | None:
        """Get a finding by its ID.

        Args:
            finding_id: The finding ID (e.g., 'MEILI-S001')

        Returns:
            The finding if found, None otherwise
        """
        for finding in self.global_findings:
            if finding.id == finding_id:
                return finding
        for index_analysis in self.indexes.values():
            for finding in index_analysis.findings:
                if finding.id == finding_id:
                    return finding
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for export."""
        return self.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"_raw_indexes"}
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisReport":
        """Create a report from a dictionary (e.g., from JSON).

        Args:
            data: Dictionary representation of the report

        Returns:
            AnalysisReport instance
        """
        return cls.model_validate(data)
