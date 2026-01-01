"""Collectors module initialization."""

from meilisearch_analyzer.collectors.live_instance import LiveInstanceCollector
from meilisearch_analyzer.collectors.base import BaseCollector

__all__ = ["LiveInstanceCollector", "BaseCollector"]
