"""JSON exporter for analysis reports."""

from pathlib import Path

import orjson

from meilisearch_analyzer.exporters.base import BaseExporter
from meilisearch_analyzer.models.report import AnalysisReport


class JsonExporter(BaseExporter):
    """Export reports to JSON format."""

    def __init__(self, pretty: bool = True):
        """Initialize the JSON exporter.

        Args:
            pretty: Whether to format output with indentation
        """
        self.pretty = pretty

    @property
    def format_name(self) -> str:
        return "json"

    @property
    def file_extension(self) -> str:
        return ".json"

    def export(self, report: AnalysisReport, output_path: Path | None = None) -> str:
        """Export the report to JSON format.

        Args:
            report: The analysis report to export
            output_path: Optional path to write the JSON to

        Returns:
            The JSON string
        """
        data = report.to_dict()

        opts = orjson.OPT_SORT_KEYS
        if self.pretty:
            opts |= orjson.OPT_INDENT_2

        json_bytes = orjson.dumps(data, option=opts)
        json_str = json_bytes.decode("utf-8")

        if output_path:
            output_path.write_text(json_str)

        return json_str
