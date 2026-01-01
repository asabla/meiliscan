"""Tests for the Dump Parser."""

import json
import tarfile
import tempfile
from pathlib import Path

import pytest

from meilisearch_analyzer.collectors.dump_parser import DumpParser
from meilisearch_analyzer.models.index import IndexSettings


class TestDumpParser:
    """Tests for DumpParser."""

    @pytest.fixture
    def mock_dump_dir(self, tmp_path: Path) -> Path:
        """Create a mock dump directory structure."""
        dump_root = tmp_path / "dump-20260101-120000"
        dump_root.mkdir()

        # Create metadata.json
        metadata = {
            "dumpVersion": "V6",
            "dbVersion": "1.7.0",
            "dumpDate": "2026-01-01T12:00:00Z",
        }
        (dump_root / "metadata.json").write_text(json.dumps(metadata))

        # Create indexes directory
        indexes_dir = dump_root / "indexes"
        indexes_dir.mkdir()

        # Create a test index
        index_dir = indexes_dir / "products"
        index_dir.mkdir()

        # Index metadata
        index_metadata = {
            "primaryKey": "id",
            "createdAt": "2025-01-01T00:00:00Z",
            "updatedAt": "2025-12-31T23:59:59Z",
        }
        (index_dir / "metadata.json").write_text(json.dumps(index_metadata))

        # Index settings
        settings = {
            "searchableAttributes": ["title", "description"],
            "filterableAttributes": ["category", "price"],
            "sortableAttributes": ["price"],
        }
        (index_dir / "settings.json").write_text(json.dumps(settings))

        # Documents (NDJSON format)
        documents = [
            {"id": 1, "title": "Product 1", "description": "Desc 1", "category": "A", "price": 10.0},
            {"id": 2, "title": "Product 2", "description": "Desc 2", "category": "B", "price": 20.0},
            {"id": 3, "title": "Product 3", "description": "Desc 3", "category": "A", "price": 30.0},
        ]
        with open(index_dir / "documents.jsonl", "w") as f:
            for doc in documents:
                f.write(json.dumps(doc) + "\n")

        # Create tasks directory
        tasks_dir = dump_root / "tasks"
        tasks_dir.mkdir()

        tasks = [
            {"uid": 1, "status": "succeeded", "type": "documentAdditionOrUpdate"},
            {"uid": 2, "status": "succeeded", "type": "settingsUpdate"},
            {"uid": 3, "status": "failed", "type": "documentAdditionOrUpdate"},
        ]
        (tasks_dir / "queue.json").write_text(json.dumps(tasks))

        return tmp_path

    @pytest.fixture
    def mock_dump_file(self, mock_dump_dir: Path) -> Path:
        """Create a mock .dump file (tar.gz)."""
        dump_file = mock_dump_dir / "test.dump"

        # Find the dump directory
        dump_root = next(d for d in mock_dump_dir.iterdir() if d.name.startswith("dump-"))

        # Create tar.gz archive
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        return dump_file

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_dump_file: Path):
        """Test successful connection to dump file."""
        parser = DumpParser(mock_dump_file)
        result = await parser.connect()

        assert result is True
        await parser.close()

    @pytest.mark.asyncio
    async def test_connect_nonexistent_file(self, tmp_path: Path):
        """Test connection fails with nonexistent file."""
        parser = DumpParser(tmp_path / "nonexistent.dump")
        result = await parser.connect()

        assert result is False

    @pytest.mark.asyncio
    async def test_connect_invalid_archive(self, tmp_path: Path):
        """Test connection fails with invalid archive."""
        invalid_file = tmp_path / "invalid.dump"
        invalid_file.write_text("not a valid tar.gz file")

        parser = DumpParser(invalid_file)
        result = await parser.connect()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_version(self, mock_dump_file: Path):
        """Test getting MeiliSearch version from dump."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        version = await parser.get_version()
        assert version == "V6"

        await parser.close()

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_dump_file: Path):
        """Test getting global stats from dump."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        stats = await parser.get_stats()

        assert stats["totalDocuments"] == 3
        assert "products" in stats["indexes"]
        assert stats["indexes"]["products"]["numberOfDocuments"] == 3
        assert stats["databaseSize"] is None  # Not available in dumps

        await parser.close()

    @pytest.mark.asyncio
    async def test_get_indexes(self, mock_dump_file: Path):
        """Test getting indexes from dump."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()

        assert len(indexes) == 1
        assert indexes[0].uid == "products"
        assert indexes[0].primary_key == "id"
        assert indexes[0].document_count == 3

        await parser.close()

    @pytest.mark.asyncio
    async def test_index_settings_loaded(self, mock_dump_file: Path):
        """Test that index settings are properly loaded."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()
        settings = indexes[0].settings

        assert settings.searchable_attributes == ["title", "description"]
        assert settings.filterable_attributes == ["category", "price"]
        assert settings.sortable_attributes == ["price"]

        await parser.close()

    @pytest.mark.asyncio
    async def test_sample_documents_loaded(self, mock_dump_file: Path):
        """Test that sample documents are loaded."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()
        sample_docs = indexes[0].sample_documents

        assert len(sample_docs) == 3
        assert sample_docs[0]["id"] == 1
        assert sample_docs[0]["title"] == "Product 1"

        await parser.close()

    @pytest.mark.asyncio
    async def test_max_sample_docs_limit(self, mock_dump_dir: Path):
        """Test that max_sample_docs limits documents loaded."""
        # Create dump with more documents
        dump_root = next(d for d in mock_dump_dir.iterdir() if d.name.startswith("dump-"))
        index_dir = dump_root / "indexes" / "products"

        # Add more documents
        with open(index_dir / "documents.jsonl", "w") as f:
            for i in range(200):
                doc = {"id": i, "title": f"Product {i}"}
                f.write(json.dumps(doc) + "\n")

        # Create new dump file
        dump_file = mock_dump_dir / "large.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        # Parse with limit
        parser = DumpParser(dump_file, max_sample_docs=50)
        await parser.connect()

        indexes = await parser.get_indexes()

        # Should have all documents counted but only 50 samples
        assert indexes[0].document_count == 200
        assert len(indexes[0].sample_documents) == 50

        await parser.close()

    @pytest.mark.asyncio
    async def test_field_distribution(self, mock_dump_file: Path):
        """Test that field distribution is calculated."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()
        field_dist = indexes[0].stats.field_distribution

        assert field_dist["id"] == 3
        assert field_dist["title"] == 3
        assert field_dist["description"] == 3
        assert field_dist["category"] == 3
        assert field_dist["price"] == 3

        await parser.close()

    @pytest.mark.asyncio
    async def test_get_tasks(self, mock_dump_file: Path):
        """Test getting tasks from dump."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        tasks = await parser.get_tasks()

        assert len(tasks) == 3
        assert tasks[0]["uid"] == 1
        assert tasks[0]["status"] == "succeeded"
        assert tasks[2]["status"] == "failed"

        await parser.close()

    @pytest.mark.asyncio
    async def test_get_tasks_empty(self, mock_dump_dir: Path):
        """Test getting tasks when tasks directory doesn't exist."""
        # Create minimal dump without tasks
        dump_root = mock_dump_dir / "dump-minimal"
        dump_root.mkdir()
        (dump_root / "metadata.json").write_text(json.dumps({"dumpVersion": "V6"}))
        (dump_root / "indexes").mkdir()

        dump_file = mock_dump_dir / "minimal.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        parser = DumpParser(dump_file)
        await parser.connect()

        tasks = await parser.get_tasks()
        assert tasks == []

        await parser.close()

    @pytest.mark.asyncio
    async def test_metadata_property(self, mock_dump_file: Path):
        """Test metadata property."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        metadata = parser.metadata

        assert metadata["dumpVersion"] == "V6"
        assert metadata["dbVersion"] == "1.7.0"

        await parser.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up(self, mock_dump_file: Path):
        """Test that close cleans up temporary files."""
        parser = DumpParser(mock_dump_file)
        await parser.connect()

        # Get temp dir path before close
        temp_dir = parser._temp_dir
        assert temp_dir is not None

        await parser.close()

        assert parser._temp_dir is None
        assert parser._extracted_path is None

    @pytest.mark.asyncio
    async def test_multiple_indexes(self, mock_dump_dir: Path):
        """Test parsing dump with multiple indexes."""
        dump_root = next(d for d in mock_dump_dir.iterdir() if d.name.startswith("dump-"))
        indexes_dir = dump_root / "indexes"

        # Create second index
        index2_dir = indexes_dir / "users"
        index2_dir.mkdir()

        (index2_dir / "metadata.json").write_text(json.dumps({"primaryKey": "user_id"}))
        (index2_dir / "settings.json").write_text(json.dumps({"searchableAttributes": ["name", "email"]}))

        with open(index2_dir / "documents.jsonl", "w") as f:
            f.write(json.dumps({"user_id": 1, "name": "Alice", "email": "alice@test.com"}) + "\n")
            f.write(json.dumps({"user_id": 2, "name": "Bob", "email": "bob@test.com"}) + "\n")

        # Create new dump file
        dump_file = mock_dump_dir / "multi.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        parser = DumpParser(dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()
        stats = await parser.get_stats()

        assert len(indexes) == 2
        index_uids = {idx.uid for idx in indexes}
        assert "products" in index_uids
        assert "users" in index_uids
        assert stats["totalDocuments"] == 5

        await parser.close()

    @pytest.mark.asyncio
    async def test_empty_index(self, mock_dump_dir: Path):
        """Test parsing index with no documents."""
        dump_root = next(d for d in mock_dump_dir.iterdir() if d.name.startswith("dump-"))
        indexes_dir = dump_root / "indexes"

        # Create empty index
        empty_dir = indexes_dir / "empty_index"
        empty_dir.mkdir()

        (empty_dir / "metadata.json").write_text(json.dumps({"primaryKey": "id"}))
        (empty_dir / "settings.json").write_text(json.dumps({}))
        (empty_dir / "documents.jsonl").write_text("")  # Empty file

        dump_file = mock_dump_dir / "with_empty.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        parser = DumpParser(dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()
        empty_idx = next((idx for idx in indexes if idx.uid == "empty_index"), None)

        assert empty_idx is not None
        assert empty_idx.document_count == 0
        assert empty_idx.sample_documents == []

        await parser.close()

    @pytest.mark.asyncio
    async def test_missing_settings_file(self, mock_dump_dir: Path):
        """Test parsing index without settings.json."""
        dump_root = next(d for d in mock_dump_dir.iterdir() if d.name.startswith("dump-"))
        indexes_dir = dump_root / "indexes"

        # Create index without settings
        no_settings_dir = indexes_dir / "no_settings"
        no_settings_dir.mkdir()

        (no_settings_dir / "metadata.json").write_text(json.dumps({"primaryKey": "id"}))
        with open(no_settings_dir / "documents.jsonl", "w") as f:
            f.write(json.dumps({"id": 1, "name": "Test"}) + "\n")

        dump_file = mock_dump_dir / "no_settings.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        parser = DumpParser(dump_file)
        await parser.connect()

        indexes = await parser.get_indexes()
        idx = next((i for i in indexes if i.uid == "no_settings"), None)

        assert idx is not None
        # Should have default settings
        assert idx.settings.searchable_attributes == ["*"]

        await parser.close()

    @pytest.mark.asyncio
    async def test_tasks_with_results_wrapper(self, mock_dump_dir: Path):
        """Test tasks file with 'results' wrapper."""
        dump_root = next(d for d in mock_dump_dir.iterdir() if d.name.startswith("dump-"))
        tasks_dir = dump_root / "tasks"

        # Write tasks with results wrapper
        tasks_data = {
            "results": [
                {"uid": 1, "status": "succeeded"},
                {"uid": 2, "status": "succeeded"},
            ]
        }
        (tasks_dir / "queue.json").write_text(json.dumps(tasks_data))

        dump_file = mock_dump_dir / "tasks_wrapper.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        parser = DumpParser(dump_file)
        await parser.connect()

        tasks = await parser.get_tasks()
        assert len(tasks) == 2

        await parser.close()

    @pytest.mark.asyncio
    async def test_version_fallback(self, mock_dump_dir: Path):
        """Test version extraction with fallback field."""
        dump_root = mock_dump_dir / "dump-v5"
        dump_root.mkdir()

        # Use 'version' instead of 'dumpVersion'
        (dump_root / "metadata.json").write_text(json.dumps({"version": "V5"}))
        (dump_root / "indexes").mkdir()

        dump_file = mock_dump_dir / "v5.dump"
        with tarfile.open(dump_file, "w:gz") as tar:
            tar.add(dump_root, arcname=dump_root.name)

        parser = DumpParser(dump_file)
        await parser.connect()

        version = await parser.get_version()
        assert version == "V5"

        await parser.close()
