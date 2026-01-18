"""Performance analyzer for MeiliSearch instances."""

import re
from collections import Counter
from datetime import datetime

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.index import IndexData


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

        # New task-based checks (P007-P010)
        findings.extend(self._check_task_backlog(tasks))
        findings.extend(self._check_tiny_indexing_tasks(tasks))
        findings.extend(self._check_oversized_indexing_tasks(tasks))
        findings.extend(self._check_error_clustering(tasks))

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

    def _check_task_backlog(self, tasks: list[dict] | None) -> list[Finding]:
        """Check for sustained task backlog (P007)."""
        findings: list[Finding] = []

        if not tasks or len(tasks) < 10:
            return findings

        # Filter finished tasks with timing info
        timed_tasks = []
        for task in tasks:
            enqueued_at = task.get("enqueuedAt")
            started_at = task.get("startedAt")
            if enqueued_at and started_at:
                try:
                    # Parse ISO timestamps
                    if isinstance(enqueued_at, str):
                        enqueued = datetime.fromisoformat(
                            enqueued_at.replace("Z", "+00:00")
                        )
                    else:
                        enqueued = enqueued_at

                    if isinstance(started_at, str):
                        started = datetime.fromisoformat(
                            started_at.replace("Z", "+00:00")
                        )
                    else:
                        started = started_at

                    queue_time = (started - enqueued).total_seconds()
                    if queue_time >= 0:
                        timed_tasks.append({"task": task, "queue_time": queue_time})
                except (ValueError, TypeError):
                    continue

        if len(timed_tasks) < 5:
            return findings

        # Calculate queue time statistics
        queue_times = [t["queue_time"] for t in timed_tasks]
        avg_queue_time = sum(queue_times) / len(queue_times)
        max_queue_time = max(queue_times)

        # P007: Sustained task backlog (average queue time > 60 seconds)
        if avg_queue_time > 60:
            # Find tasks with significant queue delay
            delayed_count = sum(1 for qt in queue_times if qt > 30)

            findings.append(
                Finding(
                    id="MEILI-P007",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.WARNING,
                    title="Sustained task queue backlog detected",
                    description=(
                        f"Tasks are waiting an average of {avg_queue_time:.0f} seconds "
                        f"in the queue before processing starts (max: {max_queue_time:.0f}s). "
                        f"{delayed_count} of {len(timed_tasks)} analyzed tasks had delays > 30s. "
                        f"This suggests the instance may be overloaded."
                    ),
                    impact="Increased latency for document updates and search freshness",
                    current_value={
                        "avg_queue_time_seconds": round(avg_queue_time, 1),
                        "max_queue_time_seconds": round(max_queue_time, 1),
                        "tasks_analyzed": len(timed_tasks),
                        "tasks_delayed": delayed_count,
                    },
                    recommended_value="< 60 seconds average queue time",
                    references=[
                        "https://www.meilisearch.com/docs/learn/async/understanding-asynchronous-operations"
                    ],
                )
            )

        return findings

    def _check_tiny_indexing_tasks(self, tasks: list[dict] | None) -> list[Finding]:
        """Check for too many tiny indexing tasks (P008)."""
        findings: list[Finding] = []

        if not tasks:
            return findings

        # Filter document addition tasks
        doc_tasks = [
            t
            for t in tasks
            if t.get("type") == "documentAdditionOrUpdate"
            and t.get("status") == "succeeded"
        ]

        if len(doc_tasks) < 20:
            return findings

        # Check details for document counts
        tiny_tasks = []
        for task in doc_tasks:
            details = task.get("details", {})
            # Check various possible detail fields
            doc_count = (
                details.get("receivedDocuments")
                or details.get("indexedDocuments")
                or details.get("providedIds")
                or 0
            )
            if isinstance(doc_count, int) and 0 < doc_count < 10:
                tiny_tasks.append(task)

        # P008: Too many tiny indexing tasks (more than 50% are tiny)
        tiny_ratio = len(tiny_tasks) / len(doc_tasks)
        if tiny_ratio > 0.5 and len(tiny_tasks) >= 10:
            findings.append(
                Finding(
                    id="MEILI-P008",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.SUGGESTION,
                    title="Many tiny indexing tasks detected",
                    description=(
                        f"{len(tiny_tasks)} of {len(doc_tasks)} document addition tasks "
                        f"({tiny_ratio * 100:.0f}%) contain fewer than 10 documents each. "
                        f"Consider batching documents client-side to reduce task overhead."
                    ),
                    impact="Increased task queue overhead, slower overall indexing throughput",
                    current_value={
                        "tiny_tasks": len(tiny_tasks),
                        "total_doc_tasks": len(doc_tasks),
                        "tiny_ratio": f"{tiny_ratio * 100:.0f}%",
                    },
                    recommended_value="Batch documents into larger groups (100-10,000 per request)",
                    references=[
                        "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                    ],
                )
            )

        return findings

    def _check_oversized_indexing_tasks(
        self, tasks: list[dict] | None
    ) -> list[Finding]:
        """Check for oversized indexing tasks (P009)."""
        findings: list[Finding] = []

        if not tasks:
            return findings

        # Filter document addition tasks with duration info
        doc_tasks = [
            t
            for t in tasks
            if t.get("type") == "documentAdditionOrUpdate" and t.get("duration")
        ]

        if not doc_tasks:
            return findings

        # Parse durations and find very slow tasks
        slow_tasks = []
        for task in doc_tasks:
            duration = task.get("duration")
            duration_seconds = None

            if isinstance(duration, str):
                # Parse ISO duration (PT1.234S or PT1M30.5S)
                match = re.search(r"PT(?:(\d+)M)?(\d+\.?\d*)S", duration)
                if match:
                    minutes = int(match.group(1) or 0)
                    seconds = float(match.group(2))
                    duration_seconds = minutes * 60 + seconds
            elif isinstance(duration, (int, float)):
                duration_seconds = duration

            if duration_seconds is not None and duration_seconds > 600:  # > 10 minutes
                details = task.get("details", {})
                doc_count = details.get("receivedDocuments") or details.get(
                    "indexedDocuments", 0
                )
                slow_tasks.append(
                    {
                        "uid": task.get("uid"),
                        "duration_seconds": duration_seconds,
                        "documents": doc_count,
                        "index": task.get("indexUid"),
                    }
                )

        # P009: Oversized indexing tasks
        if slow_tasks:
            avg_duration = sum(t["duration_seconds"] for t in slow_tasks) / len(
                slow_tasks
            )
            findings.append(
                Finding(
                    id="MEILI-P009",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.SUGGESTION,
                    title="Oversized indexing tasks detected",
                    description=(
                        f"Found {len(slow_tasks)} indexing tasks taking over 10 minutes each "
                        f"(average: {avg_duration / 60:.1f} minutes). "
                        f"Consider splitting large imports into smaller batches."
                    ),
                    impact="Long-running tasks block other operations and increase memory pressure",
                    current_value={
                        "slow_task_count": len(slow_tasks),
                        "avg_duration_minutes": round(avg_duration / 60, 1),
                        "examples": slow_tasks[:3],
                    },
                    recommended_value="Keep individual tasks under 10 minutes",
                    references=[
                        "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                    ],
                )
            )

        return findings

    def _check_error_clustering(self, tasks: list[dict] | None) -> list[Finding]:
        """Check for recurring error patterns (P010)."""
        findings: list[Finding] = []

        if not tasks:
            return findings

        # Filter failed tasks with error info
        failed_tasks = [
            t for t in tasks if t.get("status") == "failed" and t.get("error")
        ]

        if len(failed_tasks) < 3:
            return findings

        # Cluster errors by code/message
        error_codes: Counter[str] = Counter()
        error_messages: Counter[str] = Counter()
        error_examples: dict[str, dict] = {}

        for task in failed_tasks:
            error = task.get("error", {})
            code = error.get("code", "unknown")
            message = error.get("message", "")

            error_codes[code] += 1

            # Truncate message for grouping (first 100 chars)
            msg_key = message[:100] if message else "no message"
            error_messages[msg_key] += 1

            # Store example if not already present
            if code not in error_examples:
                error_examples[code] = {
                    "code": code,
                    "message": message[:200] if message else "",
                    "type": error.get("type", ""),
                    "count": 0,
                }
            error_examples[code]["count"] = error_codes[code]

        # P010: Report top recurring errors
        top_errors = error_codes.most_common(5)
        recurring_errors = [(code, count) for code, count in top_errors if count >= 3]

        if recurring_errors:
            error_summary = [
                {
                    "code": code,
                    "count": count,
                    "message": error_examples.get(code, {}).get("message", "")[:100],
                }
                for code, count in recurring_errors
            ]

            total_recurring = sum(count for _, count in recurring_errors)
            findings.append(
                Finding(
                    id="MEILI-P010",
                    category=FindingCategory.PERFORMANCE,
                    severity=FindingSeverity.WARNING,
                    title="Recurring task failures detected",
                    description=(
                        f"Found {total_recurring} failed tasks with recurring error patterns. "
                        f"Top error codes: {', '.join(code for code, _ in recurring_errors)}. "
                        f"Review and fix the root causes to improve reliability."
                    ),
                    impact="Repeated failures indicate systematic issues affecting data consistency",
                    current_value={
                        "total_failed": len(failed_tasks),
                        "recurring_errors": error_summary,
                    },
                    references=[
                        "https://www.meilisearch.com/docs/reference/errors/error_codes"
                    ],
                )
            )

        return findings
