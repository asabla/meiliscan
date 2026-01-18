"""Base collector interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from meiliscan.models.index import IndexData

if TYPE_CHECKING:
    from meiliscan.core.progress import ProgressCallback


class BaseCollector(ABC):
    """Abstract base class for data collectors."""

    @abstractmethod
    async def connect(self, progress_cb: "ProgressCallback | None" = None) -> bool:
        """Establish connection to the data source.

        Args:
            progress_cb: Optional callback for progress updates
        """
        pass

    @abstractmethod
    async def get_indexes(
        self, progress_cb: "ProgressCallback | None" = None
    ) -> list[IndexData]:
        """Retrieve all indexes with their data.

        Args:
            progress_cb: Optional callback for progress updates
        """
        pass

    @abstractmethod
    async def get_version(self) -> str | None:
        """Get the MeiliSearch version."""
        pass

    @abstractmethod
    async def get_stats(self) -> dict:
        """Get global statistics."""
        pass

    async def get_tasks(self, limit: int = 1000) -> list[dict]:
        """Get task history.

        Args:
            limit: Maximum number of tasks to retrieve

        Returns:
            List of task dictionaries. Empty by default.
        """
        return []

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass
