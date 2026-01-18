"""Base exporter interface."""

from abc import ABC, abstractmethod
from pathlib import Path

from meiliscan.models.report import AnalysisReport


class BaseExporter(ABC):
    """Abstract base class for report exporters."""

    @abstractmethod
    def export(self, report: AnalysisReport, output_path: Path | None = None) -> str:
        """Export the report to the desired format.

        Args:
            report: The analysis report to export
            output_path: Optional path to write the export to

        Returns:
            The exported content as a string
        """
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Get the export format name."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Get the default file extension for this format."""
        pass
