"""Collectors module initialization."""

from meilisearch_analyzer.collectors.base import BaseCollector
from meilisearch_analyzer.collectors.dump_parser import DumpParser
from meilisearch_analyzer.collectors.live_instance import LiveInstanceCollector

__all__ = ["BaseCollector", "DumpParser", "LiveInstanceCollector"]
