"""Fix benchmark runner for before/after performance comparison."""

import asyncio
import time
from typing import TYPE_CHECKING, Any

from meiliscan.benchmarks.search_runner import SearchBenchmarkRunner
from meiliscan.models.benchmark import FixBenchmark
from meiliscan.models.finding import Finding
from meiliscan.models.index import IndexData

if TYPE_CHECKING:
    from meiliscan.collectors.live_instance import LiveInstanceCollector


class FixBenchmarkRunner:
    """Runs before/after benchmarks by applying fixes."""

    # Maximum time to wait for indexing to complete (in seconds)
    MAX_INDEXING_WAIT = 300  # 5 minutes

    # Polling interval for indexing status (in seconds)
    INDEXING_POLL_INTERVAL = 2

    def __init__(
        self,
        collector: "LiveInstanceCollector",
        seed: int | None = None,
    ):
        """Initialize the fix benchmark runner.

        Args:
            collector: Connected LiveInstanceCollector
            seed: Optional random seed for reproducibility
        """
        self._collector = collector
        self._benchmark_runner = SearchBenchmarkRunner(
            collector, seed=seed, queries_per_type=3
        )

    async def benchmark_fix(
        self,
        index: IndexData,
        finding: Finding,
        apply: bool = False,
        revert_after: bool = True,
    ) -> FixBenchmark:
        """Benchmark a fix, optionally applying it.

        Args:
            index: The index the fix applies to
            finding: The finding with the fix to apply
            apply: If True, actually apply the fix (modifies the instance!)
            revert_after: If True and apply=True, revert settings after benchmarking

        Returns:
            FixBenchmark with before/after results
        """
        # Get current settings
        current_settings = await self._collector.get_index_settings(index.uid)

        # Run "before" benchmark
        before_benchmark = await self._benchmark_runner.benchmark_index(
            index, comprehensive=True
        )

        fix_result = FixBenchmark(
            finding_id=finding.id,
            index_uid=index.uid,
            fix_description=finding.title,
            before_benchmark=before_benchmark,
            before_settings=current_settings,
            applied=False,
            reverted=False,
        )

        if not apply:
            # Dry run - just return the before benchmark
            return fix_result

        if not finding.fix:
            fix_result.error = "Finding has no fix defined"
            return fix_result

        # Apply the fix
        try:
            await self._apply_fix(index.uid, finding.fix.payload)
            fix_result.applied = True
        except Exception as e:
            fix_result.error = f"Failed to apply fix: {e}"
            return fix_result

        # Wait for indexing to complete
        try:
            indexing_start = time.perf_counter()
            await self._wait_for_indexing(index.uid)
            fix_result.indexing_duration_ms = (
                time.perf_counter() - indexing_start
            ) * 1000
            fix_result.waited_for_indexing = True
        except TimeoutError as e:
            fix_result.error = str(e)
            # Try to revert even if indexing timed out
            if revert_after:
                await self._revert_settings(index.uid, current_settings)
                fix_result.reverted = True
            return fix_result

        # Run "after" benchmark
        after_benchmark = await self._benchmark_runner.benchmark_index(
            index, comprehensive=True
        )
        fix_result.after_benchmark = after_benchmark
        fix_result.after_settings = await self._collector.get_index_settings(index.uid)

        # Calculate improvement
        before_avg = before_benchmark.avg_latency_ms
        after_avg = after_benchmark.avg_latency_ms
        if before_avg > 0:
            # Positive = improvement, negative = regression
            fix_result.improvement_percent = (
                (before_avg - after_avg) / before_avg
            ) * 100

        # Revert if requested
        if revert_after:
            try:
                await self._revert_settings(index.uid, current_settings)
                fix_result.reverted = True
            except Exception as e:
                fix_result.error = f"Failed to revert settings: {e}"

        return fix_result

    async def _apply_fix(self, index_uid: str, payload: dict[str, Any]) -> None:
        """Apply a settings fix to an index.

        Args:
            index_uid: The index to update
            payload: The settings payload to apply

        Raises:
            Exception: If the fix fails to apply
        """
        if not self._collector._client:
            raise RuntimeError("Collector not connected")

        response = await self._collector._client.patch(
            f"/indexes/{index_uid}/settings",
            json=payload,
        )
        response.raise_for_status()

        # Get task UID and wait for it
        task_info = response.json()
        task_uid = task_info.get("taskUid")
        if task_uid:
            await self._wait_for_task(task_uid)

    async def _wait_for_task(self, task_uid: int, timeout: float = 60.0) -> None:
        """Wait for a task to complete.

        Args:
            task_uid: The task UID to wait for
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If the task doesn't complete in time
            Exception: If the task fails
        """
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            task = await self._collector.get_task(task_uid)
            if task is None:
                raise Exception(f"Task {task_uid} not found")

            if task.status.value in ("succeeded", "failed", "canceled"):
                if task.status.value == "failed":
                    error_msg = task.error.message if task.error else "Unknown error"
                    raise Exception(f"Task failed: {error_msg}")
                return

            await asyncio.sleep(0.5)

        raise TimeoutError(f"Task {task_uid} did not complete within {timeout}s")

    async def _wait_for_indexing(self, index_uid: str) -> None:
        """Wait for an index to finish indexing.

        Args:
            index_uid: The index to wait for

        Raises:
            TimeoutError: If indexing doesn't complete in time
        """
        if not self._collector._client:
            raise RuntimeError("Collector not connected")

        start = time.perf_counter()
        while time.perf_counter() - start < self.MAX_INDEXING_WAIT:
            response = await self._collector._client.get(f"/indexes/{index_uid}/stats")
            response.raise_for_status()
            stats = response.json()

            if not stats.get("isIndexing", False):
                return

            await asyncio.sleep(self.INDEXING_POLL_INTERVAL)

        raise TimeoutError(
            f"Index {index_uid} still indexing after {self.MAX_INDEXING_WAIT}s"
        )

    async def _revert_settings(
        self, index_uid: str, original_settings: dict[str, Any]
    ) -> None:
        """Revert settings to their original values.

        Args:
            index_uid: The index to revert
            original_settings: The original settings to restore

        Raises:
            Exception: If reverting fails
        """
        if not self._collector._client:
            raise RuntimeError("Collector not connected")

        response = await self._collector._client.put(
            f"/indexes/{index_uid}/settings",
            json=original_settings,
        )
        response.raise_for_status()

        # Wait for the task to complete
        task_info = response.json()
        task_uid = task_info.get("taskUid")
        if task_uid:
            await self._wait_for_task(task_uid)
