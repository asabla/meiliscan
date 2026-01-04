"""Live MeiliSearch instance collector."""

from typing import Any, cast

import httpx

from meiliscan.collectors.base import BaseCollector
from meiliscan.models.index import IndexData, IndexSettings, IndexStats
from meiliscan.models.task import Task, TasksResponse, TasksSummary


class LiveInstanceCollector(BaseCollector):
    """Collector for live MeiliSearch instances."""

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        sample_docs: int | None = 20,
    ):
        """Initialize the collector.

        Args:
            url: MeiliSearch instance URL
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            sample_docs: Number of sample documents to fetch per index.
                        If None, fetch all documents.
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.sample_docs = sample_docs
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

            # Get sample documents (or all if sample_docs is None)
            sample_docs: list[dict[str, Any]] = []
            try:
                if self.sample_docs is None:
                    # Fetch all documents with pagination
                    offset = 0
                    batch_size = 1000  # MeiliSearch default max limit
                    while True:
                        docs_response = await self._client.get(
                            f"/indexes/{uid}/documents",
                            params={"limit": batch_size, "offset": offset},
                        )
                        docs_response.raise_for_status()
                        docs_data = docs_response.json()

                        if isinstance(docs_data, dict) and "results" in docs_data:
                            batch = cast(list[dict[str, Any]], docs_data["results"])
                        elif isinstance(docs_data, list):
                            batch = cast(list[dict[str, Any]], docs_data)
                        else:
                            break

                        if not batch:
                            break

                        sample_docs.extend(batch)
                        offset += len(batch)

                        # Check if we've fetched all documents
                        if len(batch) < batch_size:
                            break
                else:
                    # Fetch limited sample
                    docs_response = await self._client.get(
                        f"/indexes/{uid}/documents",
                        params={"limit": self.sample_docs},
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

    async def get_tasks_paginated(
        self,
        limit: int = 20,
        from_uid: int | None = None,
        statuses: list[str] | None = None,
        types: list[str] | None = None,
        index_uids: list[str] | None = None,
    ) -> TasksResponse:
        """Get tasks with pagination and filtering.

        Args:
            limit: Maximum number of tasks to retrieve per page
            from_uid: Start from this task UID (for pagination)
            statuses: Filter by task status (succeeded, failed, etc.)
            types: Filter by task type (documentAdditionOrUpdate, etc.)
            index_uids: Filter by index UID

        Returns:
            TasksResponse with tasks and pagination info
        """
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        params: dict[str, Any] = {"limit": limit}
        if from_uid is not None:
            params["from"] = from_uid
        if statuses:
            params["statuses"] = ",".join(statuses)
        if types:
            params["types"] = ",".join(types)
        if index_uids:
            params["indexUids"] = ",".join(index_uids)

        response = await self._client.get("/tasks", params=params)
        response.raise_for_status()
        data = response.json()

        return TasksResponse(**data)

    async def get_task(self, task_uid: int) -> Task | None:
        """Get a single task by UID.

        Args:
            task_uid: The task UID to retrieve

        Returns:
            Task object or None if not found
        """
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        try:
            response = await self._client.get(f"/tasks/{task_uid}")
            response.raise_for_status()
            return Task(**response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_tasks_summary(self) -> TasksSummary:
        """Get summary statistics for all tasks.

        Returns:
            TasksSummary with counts by status
        """
        # Fetch enough tasks to get good statistics
        tasks_response = await self.get_tasks_paginated(limit=1000)
        return TasksSummary.from_tasks(tasks_response.results)

    async def search(
        self,
        index_uid: str,
        query: str = "",
        filter: str | None = None,
        sort: list[str] | None = None,
        distinct: str | None = None,
        hits_per_page: int = 20,
        page: int = 1,
    ) -> dict[str, Any]:
        """Execute a search query against an index.

        Args:
            index_uid: The index to search
            query: Search query string
            filter: Filter expression string
            sort: List of sort expressions (e.g., ["price:asc", "title:desc"])
            distinct: Attribute to use for distinct results
            hits_per_page: Number of results per page
            page: Page number (1-indexed)

        Returns:
            Search results dictionary from Meilisearch
        """
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        # Build search payload
        payload: dict[str, Any] = {
            "q": query,
            "hitsPerPage": hits_per_page,
            "page": page,
        }

        if filter:
            payload["filter"] = filter

        if sort:
            payload["sort"] = sort

        if distinct:
            payload["distinct"] = distinct

        response = await self._client.post(
            f"/indexes/{index_uid}/search",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
