"""Main analyzer that coordinates analysis across multiple analyzers."""

from meilisearch_analyzer.analyzers.base import BaseAnalyzer
from meilisearch_analyzer.analyzers.document_analyzer import DocumentAnalyzer
from meilisearch_analyzer.analyzers.performance_analyzer import PerformanceAnalyzer
from meilisearch_analyzer.analyzers.schema_analyzer import SchemaAnalyzer
from meilisearch_analyzer.models.finding import Finding
from meilisearch_analyzer.models.index import IndexData


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
            ]
        else:
            self._analyzers = analyzers

        # Performance analyzer for global checks
        self._performance_analyzer = PerformanceAnalyzer()

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
                print(f"Warning: Analyzer {analyzer.name} failed on index {index.uid}: {e}")

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
    ) -> list[Finding]:
        """Run global analysis across all indexes.

        Args:
            indexes: All indexes
            global_stats: Global instance stats
            tasks: Optional task history

        Returns:
            List of global findings
        """
        return self._performance_analyzer.analyze_global(indexes, global_stats, tasks)

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
