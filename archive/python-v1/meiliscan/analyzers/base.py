"""Base analyzer interface."""

from abc import ABC, abstractmethod

from meiliscan.models.finding import Finding
from meiliscan.models.index import IndexData


class BaseAnalyzer(ABC):
    """Abstract base class for analyzers."""

    @abstractmethod
    def analyze(self, index: IndexData) -> list[Finding]:
        """Analyze an index and return findings.

        Args:
            index: The index data to analyze

        Returns:
            List of findings from the analysis
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the analyzer name."""
        pass
