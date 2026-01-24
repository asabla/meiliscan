"""Tests for LiveInstanceCollector."""

import asyncio
import time

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

    @pytest.fixture
    def collector_concurrent(self) -> LiveInstanceCollector:
        """Create a LiveInstanceCollector instance with max_concurrent=3."""
        return LiveInstanceCollector(
            url="http://localhost:7700",
            api_key="test-key",
            sample_docs=5,
            max_concurrent=3,
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_max_concurrent_parameter(self):
        """Test that max_concurrent parameter is stored correctly."""
        collector = LiveInstanceCollector(
            url="http://localhost:7700",
            max_concurrent=5,
        )
        assert collector.max_concurrent == 5

        collector_default = LiveInstanceCollector(url="http://localhost:7700")
        assert collector_default.max_concurrent == 10  # Default value

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

    @respx.mock
    @pytest.mark.asyncio
    async def test_concurrent_fetching(
        self, collector_concurrent: LiveInstanceCollector
    ):
        """Test that indexes are fetched concurrently up to max_concurrent limit."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "1.7.0"})
        )

        # Create 6 mock indexes (more than max_concurrent=3)
        all_indexes = [{"uid": f"index-{i}", "primaryKey": "id"} for i in range(6)]

        # Mock /indexes response
        respx.get("http://localhost:7700/indexes").mock(
            return_value=Response(
                200,
                json={"results": all_indexes, "offset": 0, "limit": 1000, "total": 6},
            )
        )

        # Track concurrent requests
        concurrent_count = 0
        max_concurrent_seen = 0
        lock = asyncio.Lock()

        async def delay_response(*args, **kwargs):
            nonlocal concurrent_count, max_concurrent_seen
            async with lock:
                concurrent_count += 1
                max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
            await asyncio.sleep(0.01)  # Small delay to allow overlap
            async with lock:
                concurrent_count -= 1
            return Response(
                200,
                json={
                    "searchableAttributes": ["*"],
                    "filterableAttributes": [],
                    "sortableAttributes": [],
                },
            )

        # Mock settings for each index
        for i in range(6):
            respx.get(f"http://localhost:7700/indexes/index-{i}/settings").mock(
                side_effect=delay_response
            )

        # Mock stats for each index
        for i in range(6):
            respx.get(f"http://localhost:7700/indexes/index-{i}/stats").mock(
                return_value=Response(
                    200, json={"numberOfDocuments": 100, "isIndexing": False}
                )
            )

        # Mock documents for each index
        for i in range(6):
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
        await collector_concurrent.connect()
        indexes = await collector_concurrent.get_indexes()

        # Verify we got all 6 indexes
        assert len(indexes) == 6

        # Verify concurrent requests didn't exceed max_concurrent
        # Note: max_concurrent_seen should be <= max_concurrent (3)
        # but may be less due to timing
        assert max_concurrent_seen <= 3, (
            f"Exceeded max_concurrent: {max_concurrent_seen}"
        )

        await collector_concurrent.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_single_index_parallel_requests(
        self, collector: LiveInstanceCollector
    ):
        """Test that settings, stats, and docs are fetched in parallel for each index."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "1.7.0"})
        )

        # Create 1 mock index
        respx.get("http://localhost:7700/indexes").mock(
            return_value=Response(
                200,
                json={"results": [{"uid": "test", "primaryKey": "id"}], "total": 1},
            )
        )

        # Track request order and timing
        request_times: list[tuple[str, float]] = []
        lock = asyncio.Lock()

        async def track_settings(*args, **kwargs):
            async with lock:
                request_times.append(("settings", time.time()))
            await asyncio.sleep(0.01)
            return Response(
                200,
                json={
                    "searchableAttributes": ["*"],
                    "filterableAttributes": [],
                    "sortableAttributes": [],
                },
            )

        async def track_stats(*args, **kwargs):
            async with lock:
                request_times.append(("stats", time.time()))
            await asyncio.sleep(0.01)
            return Response(200, json={"numberOfDocuments": 100, "isIndexing": False})

        async def track_docs(*args, **kwargs):
            async with lock:
                request_times.append(("docs", time.time()))
            await asyncio.sleep(0.01)
            return Response(200, json={"results": [{"id": 1}]})

        respx.get("http://localhost:7700/indexes/test/settings").mock(
            side_effect=track_settings
        )
        respx.get("http://localhost:7700/indexes/test/stats").mock(
            side_effect=track_stats
        )
        respx.get("http://localhost:7700/indexes/test/documents").mock(
            side_effect=track_docs
        )

        # Connect and get indexes
        await collector.connect()
        indexes = await collector.get_indexes()

        # Verify we got the index
        assert len(indexes) == 1

        # Verify all three types of requests were made
        request_types = [r[0] for r in request_times]
        assert "settings" in request_types
        assert "stats" in request_types
        assert "docs" in request_types

        # Verify requests started close together (within 50ms, indicating parallel execution)
        if len(request_times) >= 3:
            times = [r[1] for r in request_times]
            time_spread = max(times) - min(times)
            # They should start nearly simultaneously (parallel)
            assert time_spread < 0.05, (
                f"Requests not parallel: spread={time_spread:.3f}s"
            )

        await collector.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_index_uids_paginated(self, collector: LiveInstanceCollector):
        """Test that list_index_uids paginates and returns sorted UIDs."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "1.7.0"})
        )

        # Create 25 mock indexes with unsorted UIDs
        all_indexes = [{"uid": f"zindex-{i}", "primaryKey": "id"} for i in range(15)]
        all_indexes += [{"uid": f"aindex-{i}", "primaryKey": "id"} for i in range(10)]

        first_batch = all_indexes[:20]
        second_batch = all_indexes[20:]

        # Mock paginated /indexes responses
        # The code uses batch_size=1000, so we simulate a scenario where
        # the first response indicates more items exist via total > len(results)
        # and the batch size equals the limit (triggering pagination logic)
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

        # Connect and list index UIDs
        await collector.connect()
        uids = await collector.list_index_uids()

        # Verify we got all 25 UIDs
        assert len(uids) == 25

        # Verify UIDs are sorted
        assert uids == sorted(uids)

        # Verify aindex-* comes before zindex-*
        assert uids[0].startswith("aindex")
        assert uids[-1].startswith("zindex")

        await collector.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_index_uids_legacy_format(
        self, collector: LiveInstanceCollector
    ):
        """Test list_index_uids with legacy non-paginated response."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "0.28.0"})
        )

        # Plain list response (legacy format)
        all_indexes = [{"uid": f"index-{i}", "primaryKey": "id"} for i in range(3)]
        respx.get("http://localhost:7700/indexes").mock(
            return_value=Response(200, json=all_indexes)
        )

        await collector.connect()
        uids = await collector.list_index_uids()

        assert len(uids) == 3
        assert uids == ["index-0", "index-1", "index-2"]

        await collector.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_index_settings(self, collector: LiveInstanceCollector):
        """Test get_index_settings fetches settings for a specific index."""
        # Mock health check
        respx.get("http://localhost:7700/health").mock(
            return_value=Response(200, json={"status": "available"})
        )

        # Mock version
        respx.get("http://localhost:7700/version").mock(
            return_value=Response(200, json={"pkgVersion": "1.7.0"})
        )

        # Mock settings endpoint
        expected_settings = {
            "searchableAttributes": ["title", "description"],
            "filterableAttributes": ["category", "price"],
            "sortableAttributes": ["price", "date"],
            "distinctAttribute": "product_id",
        }
        respx.get("http://localhost:7700/indexes/products/settings").mock(
            return_value=Response(200, json=expected_settings)
        )

        await collector.connect()
        settings = await collector.get_index_settings("products")

        assert settings == expected_settings
        assert settings["searchableAttributes"] == ["title", "description"]
        assert settings["filterableAttributes"] == ["category", "price"]
        assert settings["sortableAttributes"] == ["price", "date"]
        assert settings["distinctAttribute"] == "product_id"

        await collector.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_index_uids_not_connected(
        self, collector: LiveInstanceCollector
    ):
        """Test that list_index_uids raises error when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await collector.list_index_uids()

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_index_settings_not_connected(
        self, collector: LiveInstanceCollector
    ):
        """Test that get_index_settings raises error when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await collector.get_index_settings("test-index")
