"""Search probe analyzer for validating index configuration via test queries."""

import json
from dataclasses import dataclass
from typing import Any

from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.index import IndexData


@dataclass
class ProbeResult:
    """Result of a search probe."""

    index_uid: str
    probe_type: str  # "sort", "filter", "basic"
    success: bool
    field: str | None = None
    error_message: str | None = None
    response_size_bytes: int | None = None
    hit_count: int | None = None


class SearchProbeAnalyzer:
    """Analyzer that validates index configuration by running test queries."""

    # Maximum response payload size before warning (bytes)
    MAX_RESPONSE_SIZE = 100 * 1024  # 100KB

    # Maximum probes per index
    MAX_PROBES_PER_INDEX = 3

    @property
    def name(self) -> str:
        return "search_probe"

    async def analyze(
        self,
        indexes: list[IndexData],
        search_fn,
    ) -> tuple[list[Finding], list[ProbeResult]]:
        """Run search probes against indexes.

        Args:
            indexes: List of indexes to probe
            search_fn: Async function to execute searches.
                       Signature: search_fn(index_uid, query, filter, sort) -> dict

        Returns:
            Tuple of (findings, probe_results)
        """
        findings: list[Finding] = []
        all_probe_results: list[ProbeResult] = []

        for index in indexes:
            probe_results = await self._probe_index(index, search_fn)
            all_probe_results.extend(probe_results)

            # Generate findings from probe results
            findings.extend(self._findings_from_probes(index, probe_results))

        return findings, all_probe_results

    async def _probe_index(
        self,
        index: IndexData,
        search_fn,
    ) -> list[ProbeResult]:
        """Run probes against a single index."""
        results: list[ProbeResult] = []
        probe_count = 0

        # Basic search probe (empty query)
        if probe_count < self.MAX_PROBES_PER_INDEX:
            result = await self._probe_basic_search(index, search_fn)
            results.append(result)
            probe_count += 1

        # Sort probes
        for field in index.settings.sortable_attributes[:2]:
            if probe_count >= self.MAX_PROBES_PER_INDEX:
                break
            result = await self._probe_sort(index, search_fn, field)
            results.append(result)
            probe_count += 1

        # Filter probes
        for field in index.settings.filterable_attributes[:2]:
            if probe_count >= self.MAX_PROBES_PER_INDEX:
                break
            # Try to find a value from sample docs
            value = self._find_filter_value(index, field)
            if value is not None:
                result = await self._probe_filter(index, search_fn, field, value)
                results.append(result)
                probe_count += 1

        return results

    async def _probe_basic_search(
        self,
        index: IndexData,
        search_fn,
    ) -> ProbeResult:
        """Probe with a basic empty query."""
        try:
            response = await search_fn(
                index_uid=index.uid,
                query="",
                filter=None,
                sort=None,
            )

            # Calculate response size
            response_size = len(json.dumps(response).encode("utf-8"))
            hit_count = len(response.get("hits", []))

            return ProbeResult(
                index_uid=index.uid,
                probe_type="basic",
                success=True,
                response_size_bytes=response_size,
                hit_count=hit_count,
            )
        except Exception as e:
            return ProbeResult(
                index_uid=index.uid,
                probe_type="basic",
                success=False,
                error_message=str(e),
            )

    async def _probe_sort(
        self,
        index: IndexData,
        search_fn,
        field: str,
    ) -> ProbeResult:
        """Probe sort functionality for a field."""
        try:
            await search_fn(
                index_uid=index.uid,
                query="",
                filter=None,
                sort=[f"{field}:asc"],
            )

            return ProbeResult(
                index_uid=index.uid,
                probe_type="sort",
                field=field,
                success=True,
            )
        except Exception as e:
            return ProbeResult(
                index_uid=index.uid,
                probe_type="sort",
                field=field,
                success=False,
                error_message=str(e),
            )

    async def _probe_filter(
        self,
        index: IndexData,
        search_fn,
        field: str,
        value: Any,
    ) -> ProbeResult:
        """Probe filter functionality for a field."""
        try:
            # Build filter expression based on value type
            if isinstance(value, str):
                filter_expr = f'{field} = "{value}"'
            elif isinstance(value, bool):
                filter_expr = f"{field} = {str(value).lower()}"
            elif isinstance(value, (int, float)):
                filter_expr = f"{field} = {value}"
            else:
                filter_expr = f'{field} = "{value}"'

            await search_fn(
                index_uid=index.uid,
                query="",
                filter=filter_expr,
                sort=None,
            )

            return ProbeResult(
                index_uid=index.uid,
                probe_type="filter",
                field=field,
                success=True,
            )
        except Exception as e:
            return ProbeResult(
                index_uid=index.uid,
                probe_type="filter",
                field=field,
                success=False,
                error_message=str(e),
            )

    def _find_filter_value(self, index: IndexData, field: str) -> Any:
        """Find a sample value for a field from sample documents."""
        for doc in index.sample_documents:
            value = self._get_nested_value(doc, field)
            if value is not None and not isinstance(value, (list, dict)):
                return value
        return None

    def _get_nested_value(self, doc: dict, field: str) -> Any:
        """Get value from potentially nested field."""
        parts = field.split(".")
        current = doc
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _findings_from_probes(
        self,
        index: IndexData,
        probe_results: list[ProbeResult],
    ) -> list[Finding]:
        """Generate findings from probe results."""
        findings: list[Finding] = []

        for result in probe_results:
            if result.probe_type == "sort" and not result.success:
                # Q001: Sort probe failed
                findings.append(
                    Finding(
                        id="MEILI-Q001",
                        category=FindingCategory.SEARCH_PROBE,
                        severity=FindingSeverity.WARNING,
                        title=f"Sort on '{result.field}' failed",
                        description=(
                            f"Attempting to sort by '{result.field}' on index '{index.uid}' "
                            f"returned an error. This field is configured as sortable but "
                            f"may have incompatible data types or other issues. "
                            f"Error: {result.error_message}"
                        ),
                        impact="Sorting by this field will fail in production queries",
                        index_uid=index.uid,
                        current_value={
                            "field": result.field,
                            "error": result.error_message,
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/filtering_and_sorting/sort_search_results",
                        ],
                    )
                )

            elif result.probe_type == "filter" and not result.success:
                # Q002: Filter probe failed
                findings.append(
                    Finding(
                        id="MEILI-Q002",
                        category=FindingCategory.SEARCH_PROBE,
                        severity=FindingSeverity.WARNING,
                        title=f"Filter on '{result.field}' failed",
                        description=(
                            f"Attempting to filter by '{result.field}' on index '{index.uid}' "
                            f"returned an error. This field is configured as filterable but "
                            f"may have incompatible data or syntax issues. "
                            f"Error: {result.error_message}"
                        ),
                        impact="Filtering by this field will fail in production queries",
                        index_uid=index.uid,
                        current_value={
                            "field": result.field,
                            "error": result.error_message,
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/filtering_and_sorting/filter_search_results",
                        ],
                    )
                )

            elif result.probe_type == "basic" and result.success:
                # Q003: Large response payload
                if (
                    result.response_size_bytes is not None
                    and result.response_size_bytes > self.MAX_RESPONSE_SIZE
                ):
                    findings.append(
                        Finding(
                            id="MEILI-Q003",
                            category=FindingCategory.SEARCH_PROBE,
                            severity=FindingSeverity.INFO,
                            title="Large search response payload",
                            description=(
                                f"A basic search on index '{index.uid}' returned a response "
                                f"of {result.response_size_bytes / 1024:.1f} KB. Large responses "
                                f"increase bandwidth usage and may slow down client applications. "
                                f"Consider limiting displayedAttributes if not all fields are needed."
                            ),
                            impact="Increased bandwidth usage, slower client rendering",
                            index_uid=index.uid,
                            current_value={
                                "response_size_bytes": result.response_size_bytes,
                                "response_size_kb": round(
                                    result.response_size_bytes / 1024, 1
                                ),
                                "hit_count": result.hit_count,
                            },
                            references=[
                                "https://www.meilisearch.com/docs/learn/relevancy/displayed_searchable_attributes",
                            ],
                        )
                    )

        return findings
