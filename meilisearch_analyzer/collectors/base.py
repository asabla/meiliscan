"""Base collector interface."""

from abc import ABC, abstractmethod

from meilisearch_analyzer.models.index import IndexData


class BaseCollector(ABC):
    """Abstract base class for data collectors."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the data source."""
        pass

    @abstractmethod
    async def get_indexes(self) -> list[IndexData]:
        """Retrieve all indexes with their data."""
        pass

    @abstractmethod
    async def get_version(self) -> str | None:
        """Get the MeiliSearch version."""
        pass

    @abstractmethod
    async def get_stats(self) -> dict:
        """Get global statistics."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass
