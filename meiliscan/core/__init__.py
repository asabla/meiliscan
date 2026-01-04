"""Core module initialization."""

# Lazy imports to avoid circular dependency issues
# Users should import directly from submodules instead

__all__ = ["DataCollector", "Analyzer", "HealthScorer", "Reporter"]


def __getattr__(name: str):
    """Lazy import mechanism to avoid circular imports."""
    if name == "DataCollector":
        from meiliscan.core.collector import DataCollector

        return DataCollector
    if name == "Analyzer":
        from meiliscan.core.analyzer import Analyzer

        return Analyzer
    if name == "HealthScorer":
        from meiliscan.core.scorer import HealthScorer

        return HealthScorer
    if name == "Reporter":
        from meiliscan.core.reporter import Reporter

        return Reporter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
