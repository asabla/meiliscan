"""Data collector that orchestrates collection from various sources."""

from pathlib import Path

from meiliscan.collectors.base import BaseCollector
from meiliscan.collectors.dump_parser import DumpParser
from meiliscan.collectors.live_instance import LiveInstanceCollector
from meiliscan.models.index import IndexData


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
    ) -> "DataCollector":
        """Create a collector for a live MeiliSearch instance.

        Args:
            url: MeiliSearch instance URL
            api_key: Optional API key
            timeout: Request timeout in seconds

        Returns:
            Configured DataCollector
        """
        collector = LiveInstanceCollector(url=url, api_key=api_key, timeout=timeout)
        return cls(collector)

    @classmethod
    def from_dump(
        cls,
        dump_path: str | Path,
        max_sample_docs: int = 100,
    ) -> "DataCollector":
        """Create a collector for a MeiliSearch dump file.

        Args:
            dump_path: Path to the .dump file
            max_sample_docs: Maximum sample documents to load per index

        Returns:
            Configured DataCollector
        """
        collector = DumpParser(dump_path=dump_path, max_sample_docs=max_sample_docs)
        return cls(collector)

    async def collect(self) -> bool:
        """Collect all data from the source.

        Returns:
            True if collection was successful
        """
        if not await self._collector.connect():
            return False

        self._version = await self._collector.get_version()
        self._global_stats = await self._collector.get_stats()
        self._indexes = await self._collector.get_indexes()

        # Get tasks if available
        try:
            self._tasks = await self._collector.get_tasks()
        except Exception:
            self._tasks = []

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
