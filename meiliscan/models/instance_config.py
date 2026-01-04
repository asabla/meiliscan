"""Instance launch configuration model parsed from config.toml."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SSLConfig(BaseModel):
    """SSL configuration settings."""

    auth_path: str | None = Field(default=None, alias="ssl_auth_path")
    cert_path: str | None = Field(default=None, alias="ssl_cert_path")
    key_path: str | None = Field(default=None, alias="ssl_key_path")
    ocsp_path: str | None = Field(default=None, alias="ssl_ocsp_path")
    require_auth: bool = Field(default=False, alias="ssl_require_auth")
    resumption: bool = Field(default=False, alias="ssl_resumption")
    tickets: bool = Field(default=False, alias="ssl_tickets")

    model_config = {"populate_by_name": True}

    @property
    def is_configured(self) -> bool:
        """Check if any SSL settings are configured."""
        return bool(self.cert_path or self.key_path)


class SnapshotConfig(BaseModel):
    """Snapshot configuration settings."""

    schedule_snapshot: int | bool | None = Field(default=None)
    snapshot_dir: str = Field(default="snapshots/")
    experimental_no_snapshot_compaction: bool = Field(default=False)

    model_config = {"populate_by_name": True}

    @property
    def is_scheduled(self) -> bool:
        """Check if snapshots are scheduled."""
        if self.schedule_snapshot is None:
            return False
        if isinstance(self.schedule_snapshot, bool):
            return self.schedule_snapshot
        return self.schedule_snapshot > 0


class DumpConfig(BaseModel):
    """Dump configuration settings."""

    dump_dir: str = Field(default="dumps/")
    import_dump: str | None = Field(default=None)
    ignore_missing_dump: bool = Field(default=False)
    ignore_dump_if_db_exists: bool = Field(default=False)

    model_config = {"populate_by_name": True}


class IndexingConfig(BaseModel):
    """Indexing performance configuration."""

    max_indexing_memory: str | int | None = Field(default=None)
    max_indexing_threads: int | None = Field(default=None)
    experimental_reduce_indexing_memory_usage: bool = Field(default=False)

    model_config = {"populate_by_name": True}

    def get_memory_bytes(self) -> int | None:
        """Parse max_indexing_memory to bytes."""
        if self.max_indexing_memory is None:
            return None

        if isinstance(self.max_indexing_memory, int):
            return self.max_indexing_memory

        value = self.max_indexing_memory.strip().upper()

        # Parse human-readable sizes
        multipliers = {
            "B": 1,
            "KB": 1024,
            "MB": 1024**2,
            "GB": 1024**3,
            "TB": 1024**4,
            "KIB": 1024,
            "MIB": 1024**2,
            "GIB": 1024**3,
            "TIB": 1024**4,
        }

        for suffix, multiplier in multipliers.items():
            if value.endswith(suffix):
                try:
                    num = float(value[: -len(suffix)].strip())
                    return int(num * multiplier)
                except ValueError:
                    return None

        # Try parsing as plain number
        try:
            return int(value)
        except ValueError:
            return None


class ExperimentalConfig(BaseModel):
    """Experimental configuration settings."""

    search_queue_size: int | None = Field(
        default=None, alias="experimental_search_queue_size"
    )
    embedding_cache_entries: int | None = Field(
        default=None, alias="experimental_embedding_cache_entries"
    )
    max_number_of_batched_tasks: int | None = Field(
        default=None, alias="experimental_max_number_of_batched_tasks"
    )
    limit_batched_tasks_total_size: int | None = Field(
        default=None, alias="experimental_limit_batched_tasks_total_size"
    )
    logs_mode: str | None = Field(default=None, alias="experimental_logs_mode")
    replication_parameters: bool = Field(
        default=False, alias="experimental_replication_parameters"
    )
    dumpless_upgrade: bool = Field(default=False, alias="experimental_dumpless_upgrade")

    model_config = {"populate_by_name": True}


class InstanceLaunchConfig(BaseModel):
    """Complete instance launch configuration from config.toml."""

    # Core settings
    env: str = Field(default="development")
    master_key: str | None = Field(default=None)
    http_addr: str = Field(default="localhost:7700")
    db_path: str = Field(default="data.ms/")

    # Logging
    log_level: str = Field(default="INFO")

    # Payload
    http_payload_size_limit: int = Field(default=104857600)  # ~100MB

    # Analytics
    no_analytics: bool = Field(default=False)

    # Nested configs
    ssl: SSLConfig = Field(default_factory=SSLConfig)
    snapshot: SnapshotConfig = Field(default_factory=SnapshotConfig)
    dump: DumpConfig = Field(default_factory=DumpConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    experimental: ExperimentalConfig = Field(default_factory=ExperimentalConfig)

    # Task webhooks
    task_webhook_url: str | None = Field(default=None)
    task_webhook_authorization_header: str | None = Field(default=None)

    model_config = {"populate_by_name": True}

    @property
    def is_production(self) -> bool:
        """Check if environment is production."""
        return self.env.lower() == "production"

    @property
    def binds_to_all_interfaces(self) -> bool:
        """Check if http_addr binds to 0.0.0.0 (all interfaces)."""
        return self.http_addr.startswith("0.0.0.0:")

    @classmethod
    def from_toml_file(cls, path: str | Path) -> "InstanceLaunchConfig":
        """Parse config from a TOML file.

        Args:
            path: Path to the config.toml file

        Returns:
            Parsed InstanceLaunchConfig
        """
        import tomllib

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstanceLaunchConfig":
        """Parse config from a dictionary (typically from TOML).

        Args:
            data: Configuration dictionary

        Returns:
            Parsed InstanceLaunchConfig
        """
        # Flatten and normalize keys
        normalized = cls._normalize_config(data)

        # Build nested configs
        ssl_data = {k: v for k, v in normalized.items() if k.startswith("ssl_")}
        snapshot_data = {
            "schedule_snapshot": normalized.get("schedule_snapshot"),
            "snapshot_dir": normalized.get("snapshot_dir", "snapshots/"),
            "experimental_no_snapshot_compaction": normalized.get(
                "experimental_no_snapshot_compaction", False
            ),
        }
        dump_data = {
            "dump_dir": normalized.get("dump_dir", "dumps/"),
            "import_dump": normalized.get("import_dump"),
            "ignore_missing_dump": normalized.get("ignore_missing_dump", False),
            "ignore_dump_if_db_exists": normalized.get(
                "ignore_dump_if_db_exists", False
            ),
        }
        indexing_data = {
            "max_indexing_memory": normalized.get("max_indexing_memory"),
            "max_indexing_threads": normalized.get("max_indexing_threads"),
            "experimental_reduce_indexing_memory_usage": normalized.get(
                "experimental_reduce_indexing_memory_usage", False
            ),
        }
        experimental_data = {
            k: v for k, v in normalized.items() if k.startswith("experimental_")
        }

        return cls(
            env=normalized.get("env", "development"),
            master_key=normalized.get("master_key"),
            http_addr=normalized.get("http_addr", "localhost:7700"),
            db_path=normalized.get("db_path", "data.ms/"),
            log_level=normalized.get("log_level", "INFO"),
            http_payload_size_limit=normalized.get(
                "http_payload_size_limit", 104857600
            ),
            no_analytics=normalized.get("no_analytics", False),
            ssl=SSLConfig(**ssl_data) if ssl_data else SSLConfig(),
            snapshot=SnapshotConfig(**snapshot_data),
            dump=DumpConfig(**dump_data),
            indexing=IndexingConfig(**indexing_data),
            experimental=ExperimentalConfig(**experimental_data),
            task_webhook_url=normalized.get("task_webhook_url"),
            task_webhook_authorization_header=normalized.get(
                "task_webhook_authorization_header"
            ),
        )

    @staticmethod
    def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
        """Normalize config keys to snake_case.

        TOML config uses snake_case, but we need to handle both
        snake_case and kebab-case for flexibility.
        """
        normalized = {}
        for key, value in data.items():
            # Convert kebab-case to snake_case
            norm_key = key.replace("-", "_").lower()
            normalized[norm_key] = value
        return normalized

    def to_dict(self) -> dict[str, Any]:
        """Export config to dictionary."""
        return self.model_dump(mode="json", exclude_none=True)
