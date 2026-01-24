"""Core module initialization."""

# Lazy imports to avoid circular dependency issues
# Users should import directly from submodules instead

__all__ = ["DataCollector", "Analyzer", "Reporter", "calculate_statistics"]


def __getattr__(name: str):
    """Lazy import mechanism to avoid circular imports."""
    if name == "DataCollector":
        from meiliscan.core.collector import DataCollector

        return DataCollector
    if name == "Analyzer":
        from meiliscan.core.analyzer import Analyzer

        return Analyzer
    if name == "Reporter":
        from meiliscan.core.reporter import Reporter

        return Reporter
    if name == "calculate_statistics":
        from meiliscan.core.statistics import calculate_statistics

        return calculate_statistics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
