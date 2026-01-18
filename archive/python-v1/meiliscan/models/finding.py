"""Finding model representing analysis findings/issues."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    """Severity levels for findings."""

    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    INFO = "info"


class FindingCategory(str, Enum):
    """Categories for findings."""

    SCHEMA = "schema"
    DOCUMENTS = "documents"
    PERFORMANCE = "performance"
    BEST_PRACTICES = "best_practices"
    SECURITY = "security"
    INSTANCE_CONFIG = "instance_config"
    SEARCH_PROBE = "search_probe"


class FindingFix(BaseModel):
    """Represents a fix for a finding."""

    type: str = Field(..., description="Type of fix (e.g., 'settings_update')")
    endpoint: str = Field(..., description="API endpoint to call")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Payload for the fix"
    )


class Finding(BaseModel):
    """Represents an analysis finding/issue."""

    id: str = Field(..., description="Unique finding ID (e.g., 'MEILI-S001')")
    category: FindingCategory = Field(..., description="Category of the finding")
    severity: FindingSeverity = Field(..., description="Severity level")
    title: str = Field(..., description="Short title describing the finding")
    description: str = Field(..., description="Detailed description of the issue")
    impact: str = Field(..., description="Impact of this issue")
    index_uid: str | None = Field(
        default=None, description="Index this finding relates to"
    )
    current_value: Any = Field(
        default=None, description="Current value that caused the finding"
    )
    recommended_value: Any = Field(default=None, description="Recommended value")
    fix: FindingFix | None = Field(default=None, description="Suggested fix")
    references: list[str] = Field(default_factory=list, description="Reference URLs")
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to dictionary for export."""
        return self.model_dump(mode="json", exclude_none=True)
