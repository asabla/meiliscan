"""Dump file parser for MeiliSearch dumps."""

import json
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from meiliscan.collectors.base import BaseCollector
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


class DumpParser(BaseCollector):
    """Parser for MeiliSearch dump files.

    MeiliSearch dumps are tar.gz archives with the following structure:
    dump-{timestamp}/
    ├── metadata.json           # Version, dump date, instance UID
    ├── keys.json              # API keys (if present)
    ├── tasks/
    │   └── queue.json         # Task history
    └── indexes/
        └── {index_uid}/
            ├── metadata.json  # Index metadata, primary key
            ├── settings.json  # Complete index settings
            └── documents.jsonl # All documents (NDJSON format)
    """

    def __init__(self, dump_path: str | Path, max_sample_docs: int = 100):
        """Initialize the dump parser.

        Args:
            dump_path: Path to the .dump file
            max_sample_docs: Maximum number of sample documents to load per index
        """
        self.dump_path = Path(dump_path)
        self.max_sample_docs = max_sample_docs
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._extracted_path: Path | None = None
        self._metadata: dict[str, Any] = {}
        self._version: str | None = None
        self._indexes: list[IndexData] = []

    async def connect(self) -> bool:
        """Extract and parse the dump file."""
        if not self.dump_path.exists():
            return False

        try:
            # Create temporary directory for extraction
            self._temp_dir = tempfile.TemporaryDirectory()
            temp_path = Path(self._temp_dir.name)

            # Extract the dump
            with tarfile.open(self.dump_path, "r:gz") as tar:
                tar.extractall(temp_path)

            # Find the extracted directory (should be dump-{timestamp})
            extracted_dirs = list(temp_path.iterdir())
            if not extracted_dirs:
                return False

            self._extracted_path = extracted_dirs[0]

            # Load metadata
            metadata_path = self._extracted_path / "metadata.json"
            if metadata_path.exists():
                self._metadata = json.loads(metadata_path.read_text())
                self._version = self._metadata.get("dumpVersion") or self._metadata.get(
                    "version"
                )

            # Load indexes
            self._indexes = await self._load_indexes()

            return True
        except (tarfile.TarError, json.JSONDecodeError, OSError):
            return False

    async def _load_indexes(self) -> list[IndexData]:
        """Load all indexes from the dump."""
        indexes: list[IndexData] = []

        if not self._extracted_path:
            return indexes

        indexes_path = self._extracted_path / "indexes"
        if not indexes_path.exists():
            return indexes

        for index_dir in indexes_path.iterdir():
            if not index_dir.is_dir():
                continue

            uid = index_dir.name
            index_data = await self._load_index(index_dir, uid)
            if index_data:
                indexes.append(index_data)

        return indexes

    async def _load_index(self, index_dir: Path, uid: str) -> IndexData | None:
        """Load a single index from its directory."""
        try:
            # Load metadata
            metadata_path = index_dir / "metadata.json"
            metadata: dict[str, Any] = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())

            # Load settings
            settings_path = index_dir / "settings.json"
            settings_data: dict[str, Any] = {}
            if settings_path.exists():
                settings_data = json.loads(settings_path.read_text())

            # Load documents (sample only)
            documents_path = index_dir / "documents.jsonl"
            sample_docs: list[dict[str, Any]] = []
            field_distribution: dict[str, int] = {}
            doc_count = 0

            if documents_path.exists():
                with open(documents_path, "r") as f:
                    for i, line in enumerate(f):
                        doc_count += 1
                        doc = json.loads(line)

                        # Track field distribution
                        for field in doc.keys():
                            field_distribution[field] = (
                                field_distribution.get(field, 0) + 1
                            )

                        # Collect sample documents
                        if i < self.max_sample_docs:
                            sample_docs.append(doc)

            # Create index data
            settings = (
                IndexSettings(**settings_data) if settings_data else IndexSettings()
            )
            stats = IndexStats(
                numberOfDocuments=doc_count,
                isIndexing=False,
                fieldDistribution=field_distribution,
            )

            return IndexData(
                uid=uid,
                primaryKey=metadata.get("primaryKey"),
                createdAt=metadata.get("createdAt"),
                updatedAt=metadata.get("updatedAt"),
                settings=settings,
                stats=stats,
                sample_documents=sample_docs,
            )
        except (json.JSONDecodeError, OSError):
            return None

    async def get_version(self) -> str | None:
        """Get the MeiliSearch version from the dump."""
        return self._version

    async def get_stats(self) -> dict:
        """Get global statistics from the dump."""
        total_docs = sum(idx.document_count for idx in self._indexes)
        return {
            "databaseSize": None,  # Not available in dumps
            "indexes": {
                idx.uid: {
                    "numberOfDocuments": idx.document_count,
                    "isIndexing": False,
                }
                for idx in self._indexes
            },
            "totalDocuments": total_docs,
        }

    async def get_indexes(self) -> list[IndexData]:
        """Get all parsed indexes."""
        return self._indexes

    async def get_tasks(self, limit: int = 1000) -> list[dict]:
        """Get task history from the dump.

        Args:
            limit: Maximum number of tasks to retrieve
        """
        if not self._extracted_path:
            return []

        tasks_path = self._extracted_path / "tasks" / "queue.json"
        if not tasks_path.exists():
            return []

        try:
            data = json.loads(tasks_path.read_text())
            if isinstance(data, list):
                return data
            return data.get("results", [])
        except (json.JSONDecodeError, OSError):
            return []

    async def close(self) -> None:
        """Clean up temporary files."""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
            self._extracted_path = None

    @property
    def metadata(self) -> dict[str, Any]:
        """Get dump metadata."""
        return self._metadata
