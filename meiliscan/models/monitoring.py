"""Monitoring models for live instance tracking."""

from datetime import datetime

from pydantic import BaseModel, Field


class MonitoringSnapshot(BaseModel):
    """A single monitoring snapshot taken at a point in time."""

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the snapshot was taken"
    )
    health_check_ms: float = Field(
        default=0.0, description="Health check latency in milliseconds"
    )
    active_tasks: int = Field(default=0, description="Number of active/processing tasks")
    enqueued_tasks: int = Field(default=0, description="Number of enqueued tasks")
    is_indexing: bool = Field(
        default=False, description="Whether any index is currently indexing"
    )
    search_latency_sample_ms: float | None = Field(
        default=None, description="Sample search latency (empty query)"
    )
    total_documents: int = Field(default=0, description="Total document count")

    def to_event_dict(self) -> dict:
        """Convert to dict suitable for SSE events."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "health_check_ms": round(self.health_check_ms, 2),
            "active_tasks": self.active_tasks,
            "enqueued_tasks": self.enqueued_tasks,
            "is_indexing": self.is_indexing,
            "search_latency_sample_ms": (
                round(self.search_latency_sample_ms, 2)
                if self.search_latency_sample_ms is not None
                else None
            ),
            "total_documents": self.total_documents,
        }


class AlertConfig(BaseModel):
    """Configuration for monitoring alerts."""

    max_latency_ms: float = Field(
        default=500.0, description="Maximum acceptable search latency"
    )
    max_queue_depth: int = Field(
        default=100, description="Maximum acceptable task queue depth"
    )
    max_failure_rate: float = Field(
        default=0.1, description="Maximum acceptable task failure rate (0-1)"
    )
