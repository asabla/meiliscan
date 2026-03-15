"""File-based benchmark storage for historical comparison."""

import json
from datetime import datetime
from pathlib import Path

from meiliscan.models.benchmark import BenchmarkReport


# Default storage directory
DEFAULT_STORE_DIR = Path.home() / ".meiliscan" / "benchmarks"


class BenchmarkComparison:
    """Comparison between two benchmark reports."""

    def __init__(self, baseline: BenchmarkReport, current: BenchmarkReport):
        self.baseline = baseline
        self.current = current

    @property
    def latency_change_ms(self) -> float:
        """Overall average latency change (positive = slower)."""
        return self.current.avg_overall_ms - self.baseline.avg_overall_ms

    @property
    def latency_change_percent(self) -> float:
        """Latency change as percentage."""
        if self.baseline.avg_overall_ms == 0:
            return 0.0
        return (self.latency_change_ms / self.baseline.avg_overall_ms) * 100

    @property
    def p95_change_ms(self) -> float:
        return self.current.p95_latency_ms - self.baseline.p95_latency_ms

    @property
    def is_regression(self) -> bool:
        """Whether the current report shows a regression (>10% slower)."""
        return self.latency_change_percent > 10

    @property
    def is_improvement(self) -> bool:
        """Whether the current report shows improvement (>10% faster)."""
        return self.latency_change_percent < -10

    def per_query_type_deltas(self) -> dict[str, float]:
        """Compute latency deltas per query type across indexes."""
        deltas: dict[str, float] = {}

        query_types = ["baseline", "text", "filtered", "sorted", "faceted", "complex"]
        for qt in query_types:
            baseline_latencies = []
            current_latencies = []

            for idx in self.baseline.indexes:
                lat = getattr(idx, f"{qt}_latency_ms", None)
                if lat is not None:
                    baseline_latencies.append(lat)

            for idx in self.current.indexes:
                lat = getattr(idx, f"{qt}_latency_ms", None)
                if lat is not None:
                    current_latencies.append(lat)

            if baseline_latencies and current_latencies:
                baseline_avg = sum(baseline_latencies) / len(baseline_latencies)
                current_avg = sum(current_latencies) / len(current_latencies)
                deltas[qt] = current_avg - baseline_avg

        return deltas

    def to_dict(self) -> dict:
        """Convert comparison to a summary dict."""
        return {
            "latency_change_ms": round(self.latency_change_ms, 2),
            "latency_change_percent": round(self.latency_change_percent, 1),
            "p95_change_ms": round(self.p95_change_ms, 2),
            "is_regression": self.is_regression,
            "is_improvement": self.is_improvement,
            "per_query_type": {
                k: round(v, 2) for k, v in self.per_query_type_deltas().items()
            },
            "baseline_ran_at": self.baseline.ran_at.isoformat(),
            "current_ran_at": self.current.ran_at.isoformat(),
        }


class BenchmarkStore:
    """File-based storage for benchmark reports."""

    def __init__(self, store_dir: Path | None = None):
        self.store_dir = store_dir or DEFAULT_STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_url(self, url: str) -> str:
        """Convert URL to filesystem-safe string."""
        return url.replace("://", "_").replace("/", "_").replace(":", "_").rstrip("_")

    def _instance_dir(self, source_url: str) -> Path:
        """Get storage directory for a specific instance."""
        d = self.store_dir / self._sanitize_url(source_url)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, report: BenchmarkReport) -> Path:
        """Save a benchmark report to disk.

        Args:
            report: The benchmark report to save

        Returns:
            Path where the report was saved
        """
        instance_dir = self._instance_dir(report.source_url)
        timestamp = report.ran_at.strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_{timestamp}.json"
        filepath = instance_dir / filename

        data = report.model_dump(mode="json")
        filepath.write_text(json.dumps(data, indent=2, default=str))

        return filepath

    def load(self, filepath: Path) -> BenchmarkReport:
        """Load a benchmark report from disk.

        Args:
            filepath: Path to the saved report

        Returns:
            BenchmarkReport instance
        """
        data = json.loads(filepath.read_text())
        return BenchmarkReport.model_validate(data)

    def list_reports(self, source_url: str | None = None) -> list[dict]:
        """List available benchmark reports.

        Args:
            source_url: Optional filter by instance URL

        Returns:
            List of dicts with 'path', 'ran_at', 'source_url', 'total_queries'
        """
        reports: list[dict] = []

        if source_url:
            dirs = [self._instance_dir(source_url)]
        else:
            dirs = [d for d in self.store_dir.iterdir() if d.is_dir()]

        for d in dirs:
            for filepath in sorted(d.glob("benchmark_*.json"), reverse=True):
                try:
                    data = json.loads(filepath.read_text())
                    reports.append(
                        {
                            "path": str(filepath),
                            "ran_at": data.get("ran_at", ""),
                            "source_url": data.get("source_url", ""),
                            "total_queries": data.get("total_queries", 0),
                            "avg_overall_ms": data.get("avg_overall_ms", 0),
                        }
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

        return reports

    def compare(
        self, baseline_path: Path, current_path: Path
    ) -> BenchmarkComparison:
        """Compare two benchmark reports.

        Args:
            baseline_path: Path to the baseline report
            current_path: Path to the current report

        Returns:
            BenchmarkComparison with delta analysis
        """
        baseline = self.load(baseline_path)
        current = self.load(current_path)
        return BenchmarkComparison(baseline, current)
