"""Performance analyzer for MeiliSearch instances."""

from meilisearch_analyzer.analyzers.base import BaseAnalyzer
from meilisearch_analyzer.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meilisearch_analyzer.models.index import IndexData


class PerformanceAnalyzer(BaseAnalyzer):
    """Analyzer for performance-related metrics."""

    @property
    def name(self) -> str:
        return "performance"

    def analyze(self, index: IndexData) -> list[Finding]:
        """Analyze index for performance issues."""
        findings: list[Finding] = []

        findings.extend(self._check_field_count(index))
        findings.extend(self._check_index_balance(index))

        return findings

    def analyze_global(
        self,
        indexes: list[IndexData],
        global_stats: dict,
        tasks: list[dict] | None = None,
    ) -> list[Finding]:
        """Analyze global performance metrics.

        Args:
            indexes: All indexes in the instance
            global_stats: Global stats from the instance
            tasks: Optional task history

        Returns:
            List of global findings
        """
        findings: list[Finding] = []

        findings.extend(self._check_task_failures(tasks))
        findings.extend(self._check_slow_indexing(tasks))
        findings.extend(self._check_database_fragmentation(global_stats))
        findings.extend(self._check_index_count(indexes))
        findings.extend(self._check_index_imbalance(indexes))

        return findings

    def _check_field_count(self, index: IndexData) -> list[Finding]:
        """Check for too many fields (P006)."""
        findings: list[Finding] = []

        field_count = index.field_count

        # P006: Too many fields
        if field_count > 100:
            findings.append(
                Finding(
                    id="MEILI-P006",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.WARNING,
                    title="Too many unique fields",
                    description=(
                        f"Index has {field_count} unique fields. "
                        f"Having more than 100 fields can impact indexing performance "
                        f"and increase memory usage."
                    ),
                    impact="Increased memory usage, slower indexing",
                    index_uid=index.uid,
                    current_value=field_count,
                    recommended_value="< 100",
                    references=[
                        "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                    ],
                )
            )

        return findings

    def _check_index_balance(self, index: IndexData) -> list[Finding]:
        """Check individual index balance - placeholder for per-index checks."""
        return []

    def _check_task_failures(self, tasks: list[dict] | None) -> list[Finding]:
        """Check for high task failure rate (P001)."""
        findings: list[Finding] = []

        if not tasks:
            return findings

        total_tasks = len(tasks)
        if total_tasks < 10:
            return findings

        failed_tasks = [t for t in tasks if t.get("status") == "failed"]
        failure_rate = len(failed_tasks) / total_tasks

        # P001: High task failure rate
        if failure_rate > 0.1:  # More than 10% failures
            findings.append(
                Finding(
                    id="MEILI-P001",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.CRITICAL,
                    title="High task failure rate",
                    description=(
                        f"Task failure rate is {failure_rate * 100:.1f}% "
                        f"({len(failed_tasks)} failed out of {total_tasks}). "
                        f"Review failed tasks for recurring issues."
                    ),
                    impact="Documents may not be indexed correctly",
                    current_value=f"{failure_rate * 100:.1f}%",
                    recommended_value="< 10%",
                )
            )

        return findings

    def _check_slow_indexing(self, tasks: list[dict] | None) -> list[Finding]:
        """Check for slow indexing tasks (P002)."""
        findings: list[Finding] = []

        if not tasks:
            return findings

        # Filter document addition tasks
        indexing_tasks = [
            t
            for t in tasks
            if t.get("type") in ("documentAdditionOrUpdate", "documentDeletion")
            and t.get("status") == "succeeded"
            and t.get("duration")
        ]

        if not indexing_tasks:
            return findings

        # Calculate average duration
        durations = []
        for task in indexing_tasks:
            duration = task.get("duration")
            if isinstance(duration, str):
                # Parse duration string (e.g., "PT1.234S")
                import re

                match = re.search(r"PT?(\d+\.?\d*)S", duration)
                if match:
                    durations.append(float(match.group(1)))
            elif isinstance(duration, (int, float)):
                durations.append(duration)

        if not durations:
            return findings

        avg_duration = sum(durations) / len(durations)

        # P002: Slow indexing
        if avg_duration > 300:  # More than 5 minutes average
            findings.append(
                Finding(
                    id="MEILI-P002",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.WARNING,
                    title="Slow indexing operations",
                    description=(
                        f"Average indexing task duration is {avg_duration / 60:.1f} minutes. "
                        f"Consider optimizing document size or batch sizes."
                    ),
                    impact="Slow data updates, increased latency for new content",
                    current_value=f"{avg_duration / 60:.1f} minutes",
                    recommended_value="< 5 minutes",
                )
            )

        return findings

    def _check_database_fragmentation(self, global_stats: dict) -> list[Finding]:
        """Check for database fragmentation (P003)."""
        findings: list[Finding] = []

        db_size = global_stats.get("databaseSize")
        used_size = global_stats.get("usedDatabaseSize")

        if not db_size or not used_size or db_size == 0:
            return findings

        usage_ratio = used_size / db_size

        # P003: Database fragmentation
        if usage_ratio < 0.6:  # Less than 60% usage
            fragmentation = (1 - usage_ratio) * 100
            findings.append(
                Finding(
                    id="MEILI-P003",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.SUGGESTION,
                    title="Database fragmentation detected",
                    description=(
                        f"Database is only {usage_ratio * 100:.0f}% utilized "
                        f"({fragmentation:.0f}% fragmentation). "
                        f"Consider creating a dump and re-importing to reclaim space."
                    ),
                    impact="Increased disk usage",
                    current_value={
                        "db_size_bytes": db_size,
                        "used_size_bytes": used_size,
                        "utilization": f"{usage_ratio * 100:.0f}%",
                    },
                )
            )

        return findings

    def _check_index_count(self, indexes: list[IndexData]) -> list[Finding]:
        """Check for too many indexes (P004)."""
        findings: list[Finding] = []

        index_count = len(indexes)

        # P004: Too many indexes
        if index_count > 20:
            findings.append(
                Finding(
                    id="MEILI-P004",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.SUGGESTION,
                    title="Large number of indexes",
                    description=(
                        f"Instance has {index_count} indexes. "
                        f"Having many indexes increases memory usage and management complexity. "
                        f"Consider consolidating related data."
                    ),
                    impact="Increased memory usage, management overhead",
                    current_value=index_count,
                    recommended_value="< 20",
                )
            )

        return findings

    def _check_index_imbalance(self, indexes: list[IndexData]) -> list[Finding]:
        """Check for imbalanced indexes (P005)."""
        findings: list[Finding] = []

        if len(indexes) < 2:
            return findings

        total_docs = sum(idx.document_count for idx in indexes)
        if total_docs == 0:
            return findings

        # Find dominant index
        for index in indexes:
            if index.document_count > 0:
                ratio = index.document_count / total_docs
                if ratio > 0.8:  # One index has >80% of documents
                    findings.append(
                        Finding(
                            id="MEILI-P005",
                            category=FindingCategory.PERFORMANCE,
                            severity=FindingSeverity.INFO,
                            title="Imbalanced index distribution",
                            description=(
                                f"Index '{index.uid}' contains {ratio * 100:.0f}% "
                                f"of all documents ({index.document_count:,} of {total_docs:,}). "
                                f"This may be intentional, but verify data distribution."
                            ),
                            impact="Potential resource concentration",
                            current_value={
                                "dominant_index": index.uid,
                                "percentage": f"{ratio * 100:.0f}%",
                            },
                        )
                    )
                    break

        return findings
