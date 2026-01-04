"""Progress reporting model for analysis operations."""

from dataclasses import dataclass
from typing import Callable, Literal

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


ProgressCallback = Callable[[ProgressEvent], None]


def emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    """Emit a progress event if callback is provided.

    Args:
        callback: Optional progress callback
        event: The progress event to emit
    """
    if callback is not None:
        callback(event)


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
