"""Analyzers module initialization."""

from meilisearch_analyzer.analyzers.base import BaseAnalyzer
from meilisearch_analyzer.analyzers.best_practices import BestPracticesAnalyzer
from meilisearch_analyzer.analyzers.document_analyzer import DocumentAnalyzer
from meilisearch_analyzer.analyzers.historical import HistoricalAnalyzer
from meilisearch_analyzer.analyzers.performance_analyzer import PerformanceAnalyzer
from meilisearch_analyzer.analyzers.schema_analyzer import SchemaAnalyzer

__all__ = [
    "BaseAnalyzer",
    "BestPracticesAnalyzer",
    "DocumentAnalyzer",
    "HistoricalAnalyzer",
    "PerformanceAnalyzer",
    "SchemaAnalyzer",
]
