"""Main analyzer that coordinates analysis across multiple analyzers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.analyzers.best_practices import BestPracticesAnalyzer
from meiliscan.analyzers.document_analyzer import DocumentAnalyzer
from meiliscan.analyzers.instance_config_analyzer import InstanceConfigAnalyzer
from meiliscan.analyzers.performance_analyzer import PerformanceAnalyzer
from meiliscan.analyzers.schema_analyzer import SchemaAnalyzer
from meiliscan.models.finding import Finding
from meiliscan.models.index import IndexData
from meiliscan.models.instance_config import InstanceLaunchConfig

# Default thread pool size for parallel analyzer execution
DEFAULT_ANALYZER_THREADS = 4


class Analyzer:
    """Main analyzer that runs multiple analysis passes."""

    def __init__(
        self,
        analyzers: list[BaseAnalyzer] | None = None,
        max_threads: int = DEFAULT_ANALYZER_THREADS,
    ):
        """Initialize the analyzer.

        Args:
            analyzers: Optional list of analyzers to use. Defaults to all built-in analyzers.
            max_threads: Maximum threads for parallel analyzer execution per index.
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

        self._max_threads = max_threads

        # Analyzers for global checks
        self._performance_analyzer = PerformanceAnalyzer()
        self._best_practices_analyzer = BestPracticesAnalyzer()
        self._instance_config_analyzer = InstanceConfigAnalyzer()

    async def analyze_index(
        self, index: IndexData, detect_sensitive: bool = False
    ) -> list[Finding]:
        """Analyze a single index with all configured analyzers in parallel.

        Args:
            index: The index to analyze
            detect_sensitive: Whether to detect PII/sensitive fields in documents

        Returns:
            List of all findings from all analyzers
        """
        if not self._analyzers:
            return []

        loop = asyncio.get_event_loop()

        def run_analyzer(analyzer: BaseAnalyzer) -> list[Finding]:
            """Run a single analyzer (in thread pool)."""
            try:
                if isinstance(analyzer, DocumentAnalyzer):
                    return analyzer.analyze(index, detect_sensitive=detect_sensitive)
                else:
                    return analyzer.analyze(index)
            except Exception as e:
                print(
                    f"Warning: Analyzer {analyzer.name} failed on index {index.uid}: {e}"
                )
                return []

        # Run all analyzers in parallel using thread pool
        with ThreadPoolExecutor(max_workers=self._max_threads) as executor:
            tasks = [
                loop.run_in_executor(executor, run_analyzer, analyzer)
                for analyzer in self._analyzers
            ]
            results = await asyncio.gather(*tasks)

        # Flatten results
        findings: list[Finding] = []
        for analyzer_findings in results:
            findings.extend(analyzer_findings)

        return findings

    async def analyze_all(
        self, indexes: list[IndexData], detect_sensitive: bool = False
    ) -> dict[str, list[Finding]]:
        """Analyze all indexes.

        Args:
            indexes: List of indexes to analyze
            detect_sensitive: Whether to detect PII/sensitive fields

        Returns:
            Dictionary mapping index UID to findings
        """
        results: dict[str, list[Finding]] = {}

        for index in indexes:
            results[index.uid] = await self.analyze_index(
                index, detect_sensitive=detect_sensitive
            )

        return results

    async def analyze_global(
        self,
        indexes: list[IndexData],
        global_stats: dict[str, Any],
        tasks: list[dict[str, Any]] | None = None,
        instance_version: str | None = None,
        instance_config: InstanceLaunchConfig | None = None,
    ) -> list[Finding]:
        """Run global analysis across all indexes.

        Args:
            indexes: All indexes
            global_stats: Global instance stats
            tasks: Optional task history
            instance_version: Optional MeiliSearch version string
            instance_config: Optional instance configuration from config.toml

        Returns:
            List of global findings
        """
        loop = asyncio.get_event_loop()

        # Run global analyzers in parallel
        def run_performance_global() -> list[Finding]:
            return self._performance_analyzer.analyze_global(
                indexes, global_stats, tasks
            )

        def run_best_practices_global() -> list[Finding]:
            return self._best_practices_analyzer.analyze_global(
                indexes, global_stats, tasks, instance_version
            )

        def run_instance_config() -> list[Finding]:
            if instance_config is not None:
                return self._instance_config_analyzer.analyze(instance_config)
            return []

        with ThreadPoolExecutor(max_workers=3) as executor:
            perf_task = loop.run_in_executor(executor, run_performance_global)
            bp_task = loop.run_in_executor(executor, run_best_practices_global)
            config_task = loop.run_in_executor(executor, run_instance_config)

            results = await asyncio.gather(perf_task, bp_task, config_task)

        # Flatten results
        findings: list[Finding] = []
        for result in results:
            findings.extend(result)

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
