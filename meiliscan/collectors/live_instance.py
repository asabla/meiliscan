"""Live MeiliSearch instance collector."""

from typing import Any, cast

import httpx

from meiliscan.collectors.base import BaseCollector
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


class LiveInstanceCollector(BaseCollector):
    """Collector for live MeiliSearch instances."""

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize the collector.

        Args:
            url: MeiliSearch instance URL
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._version: str | None = None
        self._global_stats: dict | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def connect(self) -> bool:
        """Establish connection to the MeiliSearch instance."""
        self._client = httpx.AsyncClient(
            base_url=self.url,
            headers=self._get_headers(),
            timeout=self.timeout,
        )
        try:
            # Check health
            response = await self._client.get("/health")
            response.raise_for_status()

            # Get version
            version_response = await self._client.get("/version")
            version_response.raise_for_status()
            version_data = version_response.json()
            self._version = version_data.get("pkgVersion")

            return True
        except httpx.HTTPError:
            return False

    async def get_version(self) -> str | None:
        """Get the MeiliSearch version."""
        return self._version

    async def get_stats(self) -> dict:
        """Get global statistics."""
        if self._global_stats is not None:
            return self._global_stats

        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        response = await self._client.get("/stats")
        response.raise_for_status()
        self._global_stats = response.json()
        return self._global_stats or {}

    async def get_indexes(self) -> list[IndexData]:
        """Retrieve all indexes with their data."""
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        # Get list of indexes
        response = await self._client.get("/indexes")
        response.raise_for_status()
        indexes_data = response.json()

        # Handle paginated response
        if isinstance(indexes_data, dict) and "results" in indexes_data:
            indexes_list = indexes_data["results"]
        else:
            indexes_list = indexes_data

        indexes: list[IndexData] = []

        for idx_info in indexes_list:
            uid = idx_info["uid"]

            # Get settings for this index
            settings_response = await self._client.get(f"/indexes/{uid}/settings")
            settings_response.raise_for_status()
            settings_data = settings_response.json()

            # Get stats for this index
            stats_response = await self._client.get(f"/indexes/{uid}/stats")
            stats_response.raise_for_status()
            stats_data = stats_response.json()

            # Get sample documents (limit to 20)
            sample_docs: list[dict[str, Any]] = []
            try:
                docs_response = await self._client.get(
                    f"/indexes/{uid}/documents",
                    params={"limit": 20},
                )
                docs_response.raise_for_status()
                docs_data = docs_response.json()
                if isinstance(docs_data, dict) and "results" in docs_data:
                    sample_docs = cast(list[dict[str, Any]], docs_data["results"])
                elif isinstance(docs_data, list):
                    sample_docs = cast(list[dict[str, Any]], docs_data)
            except httpx.HTTPError:
                pass

            index = IndexData(
                uid=uid,
                primaryKey=idx_info.get("primaryKey"),
                createdAt=idx_info.get("createdAt"),
                updatedAt=idx_info.get("updatedAt"),
                settings=IndexSettings(**settings_data),
                stats=IndexStats(**stats_data),
                sample_documents=sample_docs,
            )
            indexes.append(index)

        return indexes

    async def get_tasks(self, limit: int = 1000) -> list[dict]:
        """Get recent task history.

        Args:
            limit: Maximum number of tasks to retrieve

        Returns:
            List of task dictionaries
        """
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        response = await self._client.get("/tasks", params={"limit": limit})
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and "results" in data:
            return data["results"]
        return data if isinstance(data, list) else []

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
