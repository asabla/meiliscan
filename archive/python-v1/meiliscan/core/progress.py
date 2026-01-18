"""Progress reporting model for analysis operations."""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Union

ProgressPhase = Literal["collect", "parse", "analyze", "report"]


@dataclass
class ProgressEvent:
    """Represents a progress update during analysis.

    Attributes:
        phase: Current phase of the operation
        message: Human-readable status message
        current: Current item number (1-based)
        total: Total number of items (if known)
        index_uid: Index being processed (if applicable)
        analyzer: Analyzer name (if applicable)
    """

    phase: ProgressPhase
    message: str
    current: int | None = None
    total: int | None = None
    index_uid: str | None = None
    analyzer: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "phase": self.phase,
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "index_uid": self.index_uid,
            "analyzer": self.analyzer,
        }


ProgressCallback = Union[
    Callable[[ProgressEvent], None],
    Callable[[ProgressEvent], Awaitable[None]],
]


def emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    """Emit a progress event if callback is provided.

    Handles both sync and async callbacks. For async callbacks,
    schedules them on the running event loop if available.

    Args:
        callback: Optional progress callback (sync or async)
        event: The progress event to emit
    """
    if callback is not None:
        result = callback(event)
        # If callback is async, schedule it on the event loop
        if inspect.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(result)
            except RuntimeError:
                # No running loop, run synchronously
                asyncio.run(result)


def emit_collect(
    callback: ProgressCallback | None,
    message: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    """Emit a collect-phase progress event.

    Args:
        callback: Optional progress callback
        message: Status message
        current: Current item number
        total: Total number of items
    """
    emit(
        callback,
        ProgressEvent(phase="collect", message=message, current=current, total=total),
    )


def emit_parse(
    callback: ProgressCallback | None,
    message: str,
    current: int | None = None,
    total: int | None = None,
    index_uid: str | None = None,
) -> None:
    """Emit a parse-phase progress event.

    Args:
        callback: Optional progress callback
        message: Status message
        current: Current item number
        total: Total number of items
        index_uid: Index being parsed
    """
    emit(
        callback,
        ProgressEvent(
            phase="parse",
            message=message,
            current=current,
            total=total,
            index_uid=index_uid,
        ),
    )


def emit_analyze(
    callback: ProgressCallback | None,
    message: str,
    current: int | None = None,
    total: int | None = None,
    index_uid: str | None = None,
    analyzer: str | None = None,
) -> None:
    """Emit an analyze-phase progress event.

    Args:
        callback: Optional progress callback
        message: Status message
        current: Current item number
        total: Total number of items
        index_uid: Index being analyzed
        analyzer: Analyzer name
    """
    emit(
        callback,
        ProgressEvent(
            phase="analyze",
            message=message,
            current=current,
            total=total,
            index_uid=index_uid,
            analyzer=analyzer,
        ),
    )
