"""Task models for MeiliSearch task queue data."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """MeiliSearch task status values."""

    ENQUEUED = "enqueued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskType(str, Enum):
    """MeiliSearch task type values."""

    INDEX_CREATION = "indexCreation"
    INDEX_UPDATE = "indexUpdate"
    INDEX_DELETION = "indexDeletion"
    INDEX_SWAP = "indexSwap"
    DOCUMENT_ADDITION_OR_UPDATE = "documentAdditionOrUpdate"
    DOCUMENT_DELETION = "documentDeletion"
    SETTINGS_UPDATE = "settingsUpdate"
    DUMP_CREATION = "dumpCreation"
    TASK_CANCELATION = "taskCancelation"
    TASK_DELETION = "taskDeletion"
    SNAPSHOT_CREATION = "snapshotCreation"


class TaskError(BaseModel):
    """Task error information."""

    message: str = ""
    code: str = ""
    type: str = ""
    link: str = ""

    model_config = {"populate_by_name": True}


class Task(BaseModel):
    """MeiliSearch task representation."""

    uid: int
    index_uid: str | None = Field(default=None, alias="indexUid")
    status: TaskStatus
    task_type: str = Field(alias="type")
    canceled_by: int | None = Field(default=None, alias="canceledBy")
    details: dict[str, Any] = Field(default_factory=dict)
    error: TaskError | None = None
    duration: str | None = None
    enqueued_at: datetime = Field(alias="enqueuedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    batch_uid: int | None = Field(default=None, alias="batchUid")

    model_config = {"populate_by_name": True}

    @property
    def is_finished(self) -> bool:
        """Check if task has completed (success, failure, or canceled)."""
        return self.status in (
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELED,
        )

    @property
    def is_success(self) -> bool:
        """Check if task succeeded."""
        return self.status == TaskStatus.SUCCEEDED

    @property
    def is_failed(self) -> bool:
        """Check if task failed."""
        return self.status == TaskStatus.FAILED

    @property
    def is_processing(self) -> bool:
        """Check if task is currently processing."""
        return self.status == TaskStatus.PROCESSING

    @property
    def is_pending(self) -> bool:
        """Check if task is enqueued (waiting)."""
        return self.status == TaskStatus.ENQUEUED

    @property
    def duration_ms(self) -> int | None:
        """Parse ISO 8601 duration to milliseconds."""
        if not self.duration:
            return None
        try:
            # Format: PT0.029890209S (seconds with fractional part)
            if self.duration.startswith("PT") and self.duration.endswith("S"):
                seconds = float(self.duration[2:-1])
                return int(seconds * 1000)
        except (ValueError, IndexError):
            pass
        return None

    def format_duration(self) -> str:
        """Format duration as human-readable string."""
        ms = self.duration_ms
        if ms is None:
            return "-"
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms / 1000:.2f}s"
        else:
            minutes = ms // 60000
            seconds = (ms % 60000) / 1000
            return f"{minutes}m {seconds:.1f}s"


class TasksResponse(BaseModel):
    """Response from MeiliSearch tasks endpoint."""

    results: list[Task] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    from_uid: int | None = Field(default=None, alias="from")
    next_uid: int | None = Field(default=None, alias="next")

    model_config = {"populate_by_name": True}


class TasksSummary(BaseModel):
    """Summary statistics for tasks."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    processing: int = 0
    enqueued: int = 0
    canceled: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        finished = self.succeeded + self.failed
        if finished == 0:
            return 100.0
        return (self.succeeded / finished) * 100

    @property
    def has_active(self) -> bool:
        """Check if there are active (processing or enqueued) tasks."""
        return self.processing > 0 or self.enqueued > 0

    @classmethod
    def from_tasks(cls, tasks: list[Task]) -> "TasksSummary":
        """Create summary from list of tasks."""
        summary = cls(total=len(tasks))
        for task in tasks:
            if task.status == TaskStatus.SUCCEEDED:
                summary.succeeded += 1
            elif task.status == TaskStatus.FAILED:
                summary.failed += 1
            elif task.status == TaskStatus.PROCESSING:
                summary.processing += 1
            elif task.status == TaskStatus.ENQUEUED:
                summary.enqueued += 1
            elif task.status == TaskStatus.CANCELED:
                summary.canceled += 1
        return summary
