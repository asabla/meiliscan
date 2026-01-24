"""Live MeiliSearch instance collector."""

import asyncio
from typing import TYPE_CHECKING, Any, cast

import httpx

from meiliscan.collectors.base import BaseCollector
from meiliscan.models.index import IndexData, IndexSettings, IndexStats
from meiliscan.models.task import Task, TasksResponse, TasksSummary

if TYPE_CHECKING:
    from meiliscan.core.progress import ProgressCallback


class LiveInstanceCollector(BaseCollector):
    """Collector for live MeiliSearch instances."""

    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        sample_docs: int | None = 20,
        max_concurrent: int = 10,
    ):
        """Initialize the collector.

        Args:
            url: MeiliSearch instance URL
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            sample_docs: Number of sample documents to fetch per index.
                        If None, fetch all documents.
            max_concurrent: Maximum number of indexes to fetch concurrently.
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.sample_docs = sample_docs
        self.max_concurrent = max_concurrent
        self._client: httpx.AsyncClient | None = None
        self._version: str | None = None
        self._global_stats: dict | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def connect(self, progress_cb: "ProgressCallback | None" = None) -> bool:
        """Establish connection to the MeiliSearch instance.

        Args:
            progress_cb: Optional callback for progress updates
        """
        from meiliscan.core.progress import emit_collect

        emit_collect(progress_cb, "Connecting to MeiliSearch...")
        self._client = httpx.AsyncClient(
            base_url=self.url,
            headers=self._get_headers(),
            timeout=self.timeout,
        )
        try:
            # Check health
            response = await self._client.get("/health")
            response.raise_for_status()

            emit_collect(progress_cb, "Fetching version...")
            # Get version
            version_response = await self._client.get("/version")
            version_response.raise_for_status()
            version_data = version_response.json()
            self._version = version_data.get("pkgVersion")

            emit_collect(progress_cb, f"Connected (version {self._version})")
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

    async def list_index_uids(self) -> list[str]:
        """Fetch just the index UIDs without settings, stats, or documents.

        This is a lightweight alternative to get_indexes() when you only need
        the list of index names (e.g., for populating a dropdown).

        Returns:
            Sorted list of index UIDs
        """
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        index_uids: list[str] = []
        offset = 0
        batch_size = 1000  # MeiliSearch max limit for indexes endpoint

        while True:
            response = await self._client.get(
                "/indexes", params={"limit": batch_size, "offset": offset}
            )
            response.raise_for_status()
            indexes_data = response.json()

            # Handle paginated response (newer MeiliSearch versions)
            if isinstance(indexes_data, dict) and "results" in indexes_data:
                batch = indexes_data["results"]
                index_uids.extend(idx["uid"] for idx in batch)

                total = indexes_data.get("total")
                # If we have total info, use it to determine if we're done
                if total is not None:
                    if len(index_uids) >= total:
                        break
                    offset += len(batch)
                # Fallback: if batch is smaller than requested, we're done
                elif len(batch) < batch_size:
                    break
                else:
                    offset += len(batch)
            else:
                # Handle non-paginated response (older MeiliSearch versions)
                if isinstance(indexes_data, list):
                    index_uids = [idx["uid"] for idx in indexes_data]
                break

        return sorted(index_uids)

    async def get_index_settings(self, index_uid: str) -> dict[str, Any]:
        """Fetch settings for a specific index.

        Args:
            index_uid: The index UID

        Returns:
            Index settings dictionary
        """
        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        response = await self._client.get(f"/indexes/{index_uid}/settings")
        response.raise_for_status()
        return response.json()

    async def _fetch_documents(self, uid: str) -> list[dict[str, Any]]:
        """Fetch sample documents for an index.

        Args:
            uid: The index UID

        Returns:
            List of sample documents
        """
        if not self._client:
            return []

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

        return sample_docs

    async def _fetch_single_index(
        self, uid: str, idx_info: dict[str, Any]
    ) -> IndexData | None:
        """Fetch all data for a single index concurrently.

        This fetches settings, stats, and documents in parallel for the given index.

        Args:
            uid: The index UID
            idx_info: The index info from the indexes list

        Returns:
            IndexData object or None if fetching failed
        """
        if not self._client:
            return None

        try:
            # Fetch settings, stats, and documents concurrently
            settings_task = self._client.get(f"/indexes/{uid}/settings")
            stats_task = self._client.get(f"/indexes/{uid}/stats")
            docs_task = self._fetch_documents(uid)

            settings_response, stats_response, sample_docs = await asyncio.gather(
                settings_task, stats_task, docs_task
            )

            settings_response.raise_for_status()
            stats_response.raise_for_status()

            settings_data = settings_response.json()
            stats_data = stats_response.json()

            return IndexData(
                uid=uid,
                primaryKey=idx_info.get("primaryKey"),
                createdAt=idx_info.get("createdAt"),
                updatedAt=idx_info.get("updatedAt"),
                settings=IndexSettings(**settings_data),
                stats=IndexStats(**stats_data),
                sample_documents=sample_docs,
            )
        except httpx.HTTPError:
            return None

    async def get_indexes(
        self, progress_cb: "ProgressCallback | None" = None
    ) -> list[IndexData]:
        """Retrieve all indexes with their data concurrently.

        This method fetches index data in parallel, controlled by max_concurrent.
        For each index, settings, stats, and documents are also fetched concurrently.

        Args:
            progress_cb: Optional callback for progress updates
        """
        from meiliscan.core.progress import emit_collect

        if not self._client:
            raise RuntimeError("Collector not connected. Call connect() first.")

        emit_collect(progress_cb, "Fetching indexes...")

        # Fetch all indexes with pagination
        indexes_list: list[dict[str, Any]] = []
        offset = 0
        batch_size = 1000  # MeiliSearch max limit for indexes endpoint

        while True:
            response = await self._client.get(
                "/indexes", params={"limit": batch_size, "offset": offset}
            )
            response.raise_for_status()
            indexes_data = response.json()

            # Handle paginated response (newer MeiliSearch versions)
            if isinstance(indexes_data, dict) and "results" in indexes_data:
                batch = indexes_data["results"]
                indexes_list.extend(batch)
                total = indexes_data.get("total")

                # Check if we've fetched all indexes
                # Use total if available, otherwise check if batch is smaller than requested
                if total is not None:
                    emit_collect(
                        progress_cb,
                        f"Fetching indexes ({len(indexes_list)}/{total})...",
                        current=len(indexes_list),
                        total=total,
                    )
                    if len(indexes_list) >= total:
                        break
                elif len(batch) < batch_size:
                    break

                offset += len(batch)
            else:
                # Handle non-paginated response (older MeiliSearch versions)
                indexes_list = indexes_data if isinstance(indexes_data, list) else []
                break

        total_indexes = len(indexes_list)
        emit_collect(
            progress_cb,
            f"Found {total_indexes} indexes",
            current=total_indexes,
            total=total_indexes,
        )

        if total_indexes == 0:
            return []

        # Use semaphore to limit concurrent index fetches
        semaphore = asyncio.Semaphore(self.max_concurrent)
        completed_count = 0
        completed_lock = asyncio.Lock()

        async def fetch_with_semaphore(
            idx_info: dict[str, Any], index_num: int
        ) -> IndexData | None:
            nonlocal completed_count
            uid = idx_info["uid"]

            async with semaphore:
                emit_collect(
                    progress_cb,
                    f"Fetching index {uid}...",
                    current=completed_count,
                    total=total_indexes,
                )

                result = await self._fetch_single_index(uid, idx_info)

                async with completed_lock:
                    completed_count += 1
                    emit_collect(
                        progress_cb,
                        f"Completed {uid} ({completed_count}/{total_indexes})",
                        current=completed_count,
                        total=total_indexes,
                    )

                return result

        # Fetch all indexes concurrently with bounded parallelism
        tasks = [
            fetch_with_semaphore(idx_info, i)
            for i, idx_info in enumerate(indexes_list, start=1)
        ]
        results = await asyncio.gather(*tasks)

        # Filter out None results (failed fetches)
        indexes = [idx for idx in results if idx is not None]

        emit_collect(
            progress_cb,
            f"Fetched {len(indexes)} indexes successfully",
            current=len(indexes),
            total=total_indexes,
        )

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
