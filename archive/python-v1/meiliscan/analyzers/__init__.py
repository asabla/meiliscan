"""Analyzers module initialization."""

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.analyzers.best_practices import BestPracticesAnalyzer
from meiliscan.analyzers.document_analyzer import DocumentAnalyzer
from meiliscan.analyzers.historical import HistoricalAnalyzer
from meiliscan.analyzers.performance_analyzer import PerformanceAnalyzer
from meiliscan.analyzers.schema_analyzer import SchemaAnalyzer

__all__ = [
    "BaseAnalyzer",
    "BestPracticesAnalyzer",
    "DocumentAnalyzer",
    "HistoricalAnalyzer",
    "PerformanceAnalyzer",
    "SchemaAnalyzer",
]
