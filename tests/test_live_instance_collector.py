"""Tests for LiveInstanceCollector."""

import pytest
import respx
from httpx import Response

from meiliscan.collectors.live_instance import LiveInstanceCollector


class TestLiveInstanceCollector:
    """Tests for LiveInstanceCollector."""

    @pytest.fixture
    def collector(self) -> LiveInstanceCollector:
        """Create a LiveInstanceCollector instance."""
        return LiveInstanceCollector(
            url="http://localhost:7700",
            api_key="test-key",
            sample_docs=5,
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_indexes_paginated(self, collector: LiveInstanceCollector):
        """Test that get_indexes paginates through all indexes."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "1.7.0"})
        )

        # Create 25 mock indexes (more than default limit of 20)
        all_indexes = [{"uid": f"index-{i}", "primaryKey": "id"} for i in range(25)]

        # First page: indexes 0-19 (batch_size is 1000, but we simulate smaller pages)
        # For testing, we'll simulate the API returning batches
        first_batch = all_indexes[:20]
        second_batch = all_indexes[20:]

        # Mock paginated /indexes responses
        respx.get("http://localhost:7700/indexes").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "results": first_batch,
                        "offset": 0,
                        "limit": 1000,
                        "total": 25,
                    },
                ),
                Response(
                    200,
                    json={
                        "results": second_batch,
                        "offset": 20,
                        "limit": 1000,
                        "total": 25,
                    },
                ),
            ]
        )

        # Mock settings for each index
        for i in range(25):
            respx.get(f"http://localhost:7700/indexes/index-{i}/settings").mock(
                return_value=Response(
                    200,
                    json={
                        "searchableAttributes": ["*"],
                        "filterableAttributes": [],
                        "sortableAttributes": [],
                    },
                )
            )

        # Mock stats for each index
        for i in range(25):
            respx.get(f"http://localhost:7700/indexes/index-{i}/stats").mock(
                return_value=Response(
                    200, json={"numberOfDocuments": 100, "isIndexing": False}
                )
            )

        # Mock documents for each index
        for i in range(25):
            respx.get(f"http://localhost:7700/indexes/index-{i}/documents").mock(
                return_value=Response(
                    200,
                    json={
                        "results": [{"id": j} for j in range(5)],
                        "offset": 0,
                        "limit": 5,
                    },
                )
            )

        # Connect and get indexes
        await collector.connect()
        indexes = await collector.get_indexes()

        # Verify we got all 25 indexes
        assert len(indexes) == 25
        assert [idx.uid for idx in indexes] == [f"index-{i}" for i in range(25)]

        await collector.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_indexes_single_page(self, collector: LiveInstanceCollector):
        """Test get_indexes with a single page of results."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "1.7.0"})
        )

        # Create 5 mock indexes (less than default limit)
        all_indexes = [{"uid": f"index-{i}", "primaryKey": "id"} for i in range(5)]

        # Mock /indexes response (single page)
        respx.get("http://localhost:7700/indexes").mock(
            return_value=Response(
                200, json={"results": all_indexes, "offset": 0, "limit": 1000}
            )
        )

        # Mock settings for each index
        for i in range(5):
            respx.get(f"http://localhost:7700/indexes/index-{i}/settings").mock(
                return_value=Response(
                    200,
                    json={
                        "searchableAttributes": ["*"],
                        "filterableAttributes": [],
                        "sortableAttributes": [],
                    },
                )
            )

        # Mock stats for each index
        for i in range(5):
            respx.get(f"http://localhost:7700/indexes/index-{i}/stats").mock(
                return_value=Response(
                    200, json={"numberOfDocuments": 100, "isIndexing": False}
                )
            )

        # Mock documents for each index
        for i in range(5):
            respx.get(f"http://localhost:7700/indexes/index-{i}/documents").mock(
                return_value=Response(
                    200,
                    json={
                        "results": [{"id": j} for j in range(5)],
                        "offset": 0,
                        "limit": 5,
                    },
                )
            )

        # Connect and get indexes
        await collector.connect()
        indexes = await collector.get_indexes()

        # Verify we got all 5 indexes
        assert len(indexes) == 5

        await collector.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_indexes_legacy_non_paginated(
        self, collector: LiveInstanceCollector
    ):
        """Test get_indexes with legacy non-paginated response (older MeiliSearch)."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "0.28.0"})
        )

        # Create mock indexes as a plain list (legacy format)
        all_indexes = [{"uid": f"index-{i}", "primaryKey": "id"} for i in range(3)]

        # Mock /indexes response (plain list, no pagination wrapper)
        respx.get("http://localhost:7700/indexes").mock(
            return_value=Response(200, json=all_indexes)
        )

        # Mock settings for each index
        for i in range(3):
            respx.get(f"http://localhost:7700/indexes/index-{i}/settings").mock(
                return_value=Response(
                    200,
                    json={
                        "searchableAttributes": ["*"],
                        "filterableAttributes": [],
                        "sortableAttributes": [],
                    },
                )
            )

        # Mock stats for each index
        for i in range(3):
            respx.get(f"http://localhost:7700/indexes/index-{i}/stats").mock(
                return_value=Response(
                    200, json={"numberOfDocuments": 100, "isIndexing": False}
                )
            )

        # Mock documents for each index
        for i in range(3):
            respx.get(f"http://localhost:7700/indexes/index-{i}/documents").mock(
                return_value=Response(
                    200,
                    json={
                        "results": [{"id": j} for j in range(5)],
                        "offset": 0,
                        "limit": 5,
                    },
                )
            )

        # Connect and get indexes
        await collector.connect()
        indexes = await collector.get_indexes()

        # Verify we got all 3 indexes
        assert len(indexes) == 3

        await collector.close()
