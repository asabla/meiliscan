"""Configuration helpers for web-triggered analyses."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class AnalysisConfig:
    """Immutable analysis configuration snapshot."""

    meili_url: str | None = None
    meili_api_key: str | None = None
    dump_path: Path | None = None
    probe_search: bool = False
    sample_documents: int | None = 20
    detect_sensitive: bool = False
    max_concurrent: int = 10
    run_benchmark: bool = False
    comprehensive_benchmark: bool = False

    @property
    def has_source(self) -> bool:
        """Whether this configuration points to a valid data source."""
        return bool(self.meili_url or self.dump_path)


def clamp_sample_documents(sample_documents: int, sample_all: str) -> int | None:
    """Parse and validate sample document options from form inputs."""
    if sample_all == "true":
        return None
    return max(1, min(sample_documents, 10000))


def parse_checkbox(value: str) -> bool:
    """Parse checkbox-like values from HTML forms."""
    return value == "true"
