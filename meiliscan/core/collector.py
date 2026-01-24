"""Data collector that orchestrates collection from various sources."""

from pathlib import Path
from typing import Any

from meiliscan.collectors.base import BaseCollector
from meiliscan.collectors.dump_parser import DumpParser
from meiliscan.collectors.live_instance import LiveInstanceCollector
from meiliscan.core.progress import ProgressCallback, emit_collect
from meiliscan.models.index import IndexData

# Default concurrency limit for parallel index fetching
DEFAULT_MAX_CONCURRENT = 10


class DataCollector:
    """Orchestrates data collection from MeiliSearch sources."""

    def __init__(self, collector: BaseCollector):
        """Initialize with a specific collector.

        Args:
            collector: The collector implementation to use
        """
        self._collector = collector
        self._indexes: list[IndexData] = []
        self._global_stats: dict = {}
        self._version: str | None = None
        self._tasks: list[dict] = []

    @classmethod
    def from_url(
        cls,
        url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        sample_docs: int | None = 20,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> "DataCollector":
        """Create a collector for a live MeiliSearch instance.

        Args:
            url: MeiliSearch instance URL
            api_key: Optional API key
            timeout: Request timeout in seconds
            sample_docs: Number of sample documents to fetch per index (None = all)
            max_concurrent: Maximum number of indexes to fetch concurrently

        Returns:
            Configured DataCollector
        """
        collector = LiveInstanceCollector(
            url=url,
            api_key=api_key,
            timeout=timeout,
            sample_docs=sample_docs,
            max_concurrent=max_concurrent,
        )
        return cls(collector)

    @classmethod
    def from_dump(
        cls,
        dump_path: str | Path,
        max_sample_docs: int | None = 100,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        field_sample_size: int | None = 1000,
    ) -> "DataCollector":
        """Create a collector for a MeiliSearch dump file.

        Args:
            dump_path: Path to the .dump file
            max_sample_docs: Maximum sample documents to load per index (None = all)
            max_concurrent: Maximum number of indexes to parse concurrently
            field_sample_size: Number of documents to sample for field distribution.
                              If None, scan all documents (slower but 100% accurate).
                              Default 1000 provides ~2.5x speedup.

        Returns:
            Configured DataCollector
        """
        collector = DumpParser(
            dump_path=dump_path,
            max_sample_docs=max_sample_docs,
            max_concurrent=max_concurrent,
            field_sample_size=field_sample_size,
        )
        return cls(collector)

    async def collect(self, progress_cb: ProgressCallback | None = None) -> bool:
        """Collect all data from the source.

        Args:
            progress_cb: Optional callback for progress updates

        Returns:
            True if collection was successful
        """
        if not await self._collector.connect(progress_cb):
            return False

        emit_collect(progress_cb, "Fetching version...")
        self._version = await self._collector.get_version()

        emit_collect(progress_cb, "Fetching global stats...")
        self._global_stats = await self._collector.get_stats()

        self._indexes = await self._collector.get_indexes(progress_cb)

        # Get tasks if available
        emit_collect(progress_cb, "Fetching tasks...")
        try:
            self._tasks = await self._collector.get_tasks()
        except Exception:
            self._tasks = []

        emit_collect(
            progress_cb,
            f"Collection complete: {len(self._indexes)} indexes",
            current=len(self._indexes),
            total=len(self._indexes),
        )

        return True

    @property
    def indexes(self) -> list[IndexData]:
        """Get collected indexes."""
        return self._indexes

    @property
    def version(self) -> str | None:
        """Get MeiliSearch version."""
        return self._version

    @property
    def global_stats(self) -> dict:
        """Get global statistics."""
        return self._global_stats

    @property
    def tasks(self) -> list[dict]:
        """Get task history."""
        return self._tasks

    async def get_tasks(self, limit: int = 1000) -> list[dict]:
        """Get tasks from the underlying collector.

        Args:
            limit: Maximum number of tasks to retrieve

        Returns:
            List of task dictionaries
        """
        return await self._collector.get_tasks(limit=limit)

    async def close(self) -> None:
        """Close the underlying collector."""
        await self._collector.close()

    async def search(
        self,
        index_uid: str,
        query: str = "",
        filter: str | None = None,
        sort: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a search query (only available for live instances).

        Args:
            index_uid: Index to search
            query: Search query
            filter: Optional filter expression
            sort: Optional sort parameters

        Returns:
            Search results

        Raises:
            NotImplementedError: If the collector doesn't support search
        """
        if isinstance(self._collector, LiveInstanceCollector):
            return await self._collector.search(
                index_uid=index_uid,
                query=query,
                filter=filter,
                sort=sort,
            )
        raise NotImplementedError("Search is only available for live instances")
