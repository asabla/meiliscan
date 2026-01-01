"""Main analyzer that coordinates analysis across multiple analyzers."""

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.analyzers.best_practices import BestPracticesAnalyzer
from meiliscan.analyzers.document_analyzer import DocumentAnalyzer
from meiliscan.analyzers.performance_analyzer import PerformanceAnalyzer
from meiliscan.analyzers.schema_analyzer import SchemaAnalyzer
from meiliscan.models.finding import Finding
from meiliscan.models.index import IndexData


class Analyzer:
    """Main analyzer that runs multiple analysis passes."""

    def __init__(self, analyzers: list[BaseAnalyzer] | None = None):
        """Initialize the analyzer.

        Args:
            analyzers: Optional list of analyzers to use. Defaults to all built-in analyzers.
        """
        if analyzers is None:
            # Default set of analyzers
            self._analyzers: list[BaseAnalyzer] = [
                SchemaAnalyzer(),
                DocumentAnalyzer(),
                PerformanceAnalyzer(),
                BestPracticesAnalyzer(),
            ]
        else:
            self._analyzers = analyzers

        # Analyzers for global checks
        self._performance_analyzer = PerformanceAnalyzer()
        self._best_practices_analyzer = BestPracticesAnalyzer()

    def analyze_index(self, index: IndexData) -> list[Finding]:
        """Analyze a single index with all configured analyzers.

        Args:
            index: The index to analyze

        Returns:
            List of all findings from all analyzers
        """
        findings: list[Finding] = []

        for analyzer in self._analyzers:
            try:
                analyzer_findings = analyzer.analyze(index)
                findings.extend(analyzer_findings)
            except Exception as e:
                # Log error but continue with other analyzers
                print(
                    f"Warning: Analyzer {analyzer.name} failed on index {index.uid}: {e}"
                )

        return findings

    def analyze_all(self, indexes: list[IndexData]) -> dict[str, list[Finding]]:
        """Analyze all indexes.

        Args:
            indexes: List of indexes to analyze

        Returns:
            Dictionary mapping index UID to findings
        """
        results: dict[str, list[Finding]] = {}

        for index in indexes:
            results[index.uid] = self.analyze_index(index)

        return results

    def analyze_global(
        self,
        indexes: list[IndexData],
        global_stats: dict,
        tasks: list[dict] | None = None,
        instance_version: str | None = None,
    ) -> list[Finding]:
        """Run global analysis across all indexes.

        Args:
            indexes: All indexes
            global_stats: Global instance stats
            tasks: Optional task history
            instance_version: Optional MeiliSearch version string

        Returns:
            List of global findings
        """
        findings: list[Finding] = []

        # Performance global checks
        findings.extend(
            self._performance_analyzer.analyze_global(indexes, global_stats, tasks)
        )

        # Best practices global checks
        findings.extend(
            self._best_practices_analyzer.analyze_global(
                indexes, global_stats, tasks, instance_version
            )
        )

        return findings

    def add_analyzer(self, analyzer: BaseAnalyzer) -> None:
        """Add an analyzer to the analysis pipeline.

        Args:
            analyzer: The analyzer to add
        """
        self._analyzers.append(analyzer)

    @property
    def analyzers(self) -> list[BaseAnalyzer]:
        """Get the list of configured analyzers."""
        return self._analyzers
