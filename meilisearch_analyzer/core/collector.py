"""Data collector that orchestrates collection from various sources."""

from meilisearch_analyzer.collectors.base import BaseCollector
from meilisearch_analyzer.collectors.live_instance import LiveInstanceCollector
from meilisearch_analyzer.models.index import IndexData


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

    async def close(self) -> None:
        """Close the underlying collector."""
        await self._collector.close()
