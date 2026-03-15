"""Shared constants and utilities for route modules."""

# Valid export formats
EXPORT_FORMATS = ("json", "markdown", "sarif", "agent")

# Severity order for sorting (lower number = higher priority)
SEVERITY_ORDER = {
    "critical": 0,
    "warning": 1,
    "suggestion": 2,
    "info": 3,
}


def sort_findings_by_severity(findings: list) -> list:
    """Sort findings by severity (critical first, then warning, suggestion, info)."""
    return sorted(
        findings,
        key=lambda f: SEVERITY_ORDER.get(f.severity.value.lower(), 4),
    )
