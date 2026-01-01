"""Document analyzer for MeiliSearch index documents."""

import re
import sys
from typing import Any

from meilisearch_analyzer.analyzers.base import BaseAnalyzer
from meilisearch_analyzer.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meilisearch_analyzer.models.index import IndexData


class DocumentAnalyzer(BaseAnalyzer):
    """Analyzer for document structure and content."""

    # HTML tag detection pattern
    HTML_PATTERN = re.compile(r"<[^>]+>")

    # Common markup patterns
    MARKUP_PATTERNS = [
        re.compile(r"<[^>]+>"),  # HTML tags
        re.compile(r"\[.*?\]\(.*?\)"),  # Markdown links
        re.compile(r"#{1,6}\s"),  # Markdown headers
        re.compile(r"\*{1,2}[^*]+\*{1,2}"),  # Bold/italic
    ]

    @property
    def name(self) -> str:
        return "documents"

    def analyze(self, index: IndexData) -> list[Finding]:
        """Analyze index documents."""
        findings: list[Finding] = []

        # Need sample documents to analyze
        if not index.sample_documents:
            return findings

        findings.extend(self._check_document_size(index))
        findings.extend(self._check_schema_consistency(index))
        findings.extend(self._check_nesting_depth(index))
        findings.extend(self._check_array_sizes(index))
        findings.extend(self._check_markup_content(index))
        findings.extend(self._check_empty_fields(index))
        findings.extend(self._check_mixed_types(index))
        findings.extend(self._check_text_length(index))

        return findings

    def _check_document_size(self, index: IndexData) -> list[Finding]:
        """Check document sizes (D001)."""
        findings: list[Finding] = []

        sizes = []
        for doc in index.sample_documents:
            # Estimate size by converting to JSON string
            import json

            doc_str = json.dumps(doc)
            sizes.append(len(doc_str.encode("utf-8")))

        if not sizes:
            return findings

        avg_size = sum(sizes) / len(sizes)
        max_size = max(sizes)

        # D001: Large documents
        if avg_size > 10 * 1024 or max_size > 100 * 1024:  # 10KB avg or 100KB max
            findings.append(
                Finding(
                    id="MEILI-D001",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Large documents detected",
                    description=(
                        f"Documents are larger than recommended. "
                        f"Average size: {avg_size / 1024:.1f}KB, "
                        f"Max size: {max_size / 1024:.1f}KB. "
                        f"Large documents slow down indexing and search."
                    ),
                    impact="Slower indexing and search performance",
                    index_uid=index.uid,
                    current_value={
                        "avg_size_bytes": int(avg_size),
                        "max_size_bytes": max_size,
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                    ],
                )
            )

        return findings

    def _check_schema_consistency(self, index: IndexData) -> list[Finding]:
        """Check schema consistency across documents (D002)."""
        findings: list[Finding] = []

        if not index.sample_documents:
            return findings

        # Count field occurrences
        field_counts: dict[str, int] = {}
        total_docs = len(index.sample_documents)

        for doc in index.sample_documents:
            for field in doc.keys():
                field_counts[field] = field_counts.get(field, 0) + 1

        # Find inconsistent fields (present in less than 80% of documents)
        inconsistent_fields = [
            field
            for field, count in field_counts.items()
            if count < total_docs * 0.8 and count > total_docs * 0.2
        ]

        # D002: Inconsistent schema
        if inconsistent_fields and total_docs >= 10:
            findings.append(
                Finding(
                    id="MEILI-D002",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Inconsistent document schema",
                    description=(
                        f"Some fields appear in only some documents: {inconsistent_fields[:5]}. "
                        f"This may indicate schema issues or optional fields that could be normalized."
                    ),
                    impact="Potential search and filter inconsistencies",
                    index_uid=index.uid,
                    current_value=inconsistent_fields[:10],
                )
            )

        return findings

    def _check_nesting_depth(self, index: IndexData) -> list[Finding]:
        """Check document nesting depth (D003)."""
        findings: list[Finding] = []

        max_depth = 0
        for doc in index.sample_documents:
            depth = self._get_max_depth(doc)
            max_depth = max(max_depth, depth)

        # D003: Deep nesting
        if max_depth > 3:
            findings.append(
                Finding(
                    id="MEILI-D003",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Deep document nesting",
                    description=(
                        f"Documents have nesting depth of {max_depth}. "
                        f"MeiliSearch flattens nested objects, which can lead to "
                        f"unexpected field names and search behavior."
                    ),
                    impact="Flattened field names, potential search issues",
                    index_uid=index.uid,
                    current_value=max_depth,
                    recommended_value=3,
                    references=[
                        "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                    ],
                )
            )

        return findings

    def _get_max_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Recursively get maximum nesting depth."""
        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(
                self._get_max_depth(v, current_depth + 1) for v in obj.values()
            )
        elif isinstance(obj, list):
            if not obj:
                return current_depth
            return max(self._get_max_depth(item, current_depth) for item in obj)
        return current_depth

    def _check_array_sizes(self, index: IndexData) -> list[Finding]:
        """Check array field sizes (D004)."""
        findings: list[Finding] = []

        array_stats: dict[str, list[int]] = {}

        for doc in index.sample_documents:
            self._collect_array_stats(doc, "", array_stats)

        # Find large arrays
        large_arrays = []
        for field, sizes in array_stats.items():
            avg_size = sum(sizes) / len(sizes)
            if avg_size > 50:
                large_arrays.append((field, avg_size))

        # D004: Large arrays
        if large_arrays:
            findings.append(
                Finding(
                    id="MEILI-D004",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Large array fields detected",
                    description=(
                        f"Array fields with high average element count: "
                        f"{', '.join(f'{f} ({s:.0f} items)' for f, s in large_arrays[:3])}. "
                        f"Large arrays can slow down filtering operations."
                    ),
                    impact="Slower filtering and faceting",
                    index_uid=index.uid,
                    current_value={f: int(s) for f, s in large_arrays[:5]},
                )
            )

        return findings

    def _collect_array_stats(
        self, obj: Any, prefix: str, stats: dict[str, list[int]]
    ) -> None:
        """Recursively collect array size statistics."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                self._collect_array_stats(value, new_prefix, stats)
        elif isinstance(obj, list):
            if prefix not in stats:
                stats[prefix] = []
            stats[prefix].append(len(obj))
            for item in obj:
                self._collect_array_stats(item, prefix, stats)

    def _check_markup_content(self, index: IndexData) -> list[Finding]:
        """Check for HTML/Markdown in text fields (D005)."""
        findings: list[Finding] = []

        fields_with_markup: set[str] = set()

        for doc in index.sample_documents:
            self._find_markup_fields(doc, "", fields_with_markup)

        # D005: HTML in text fields
        if fields_with_markup:
            findings.append(
                Finding(
                    id="MEILI-D005",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.SUGGESTION,
                    title="HTML/Markdown content in text fields",
                    description=(
                        f"Fields contain HTML or Markdown markup: {list(fields_with_markup)[:5]}. "
                        f"Consider stripping markup before indexing for better search results."
                    ),
                    impact="Markup tags may appear in search results",
                    index_uid=index.uid,
                    current_value=list(fields_with_markup)[:10],
                )
            )

        return findings

    def _find_markup_fields(
        self, obj: Any, prefix: str, markup_fields: set[str]
    ) -> None:
        """Find fields containing markup."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                self._find_markup_fields(value, new_prefix, markup_fields)
        elif isinstance(obj, str) and len(obj) > 10:
            for pattern in self.MARKUP_PATTERNS:
                if pattern.search(obj):
                    markup_fields.add(prefix)
                    break

    def _check_empty_fields(self, index: IndexData) -> list[Finding]:
        """Check for empty/null field values (D006)."""
        findings: list[Finding] = []

        field_empty_counts: dict[str, int] = {}
        field_total_counts: dict[str, int] = {}

        for doc in index.sample_documents:
            self._count_empty_fields(doc, "", field_empty_counts, field_total_counts)

        # Find fields with high empty ratio
        high_empty_fields = []
        for field, empty_count in field_empty_counts.items():
            total = field_total_counts.get(field, 0)
            if total > 0:
                ratio = empty_count / total
                if ratio > 0.3:  # More than 30% empty
                    high_empty_fields.append((field, ratio))

        # D006: Empty field values
        if high_empty_fields:
            findings.append(
                Finding(
                    id="MEILI-D006",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.INFO,
                    title="High empty/null field ratio",
                    description=(
                        f"Fields with >30% null/empty values: "
                        f"{', '.join(f'{f} ({r*100:.0f}%)' for f, r in high_empty_fields[:3])}. "
                        f"Consider if these fields should be optional or if data quality could be improved."
                    ),
                    impact="Wasted storage, potential search inconsistencies",
                    index_uid=index.uid,
                    current_value={f: f"{r*100:.0f}%" for f, r in high_empty_fields[:5]},
                )
            )

        return findings

    def _count_empty_fields(
        self,
        obj: Any,
        prefix: str,
        empty_counts: dict[str, int],
        total_counts: dict[str, int],
    ) -> None:
        """Count empty field occurrences."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                total_counts[new_prefix] = total_counts.get(new_prefix, 0) + 1

                if value is None or value == "" or value == [] or value == {}:
                    empty_counts[new_prefix] = empty_counts.get(new_prefix, 0) + 1
                elif isinstance(value, (dict, list)):
                    self._count_empty_fields(value, new_prefix, empty_counts, total_counts)

    def _check_mixed_types(self, index: IndexData) -> list[Finding]:
        """Check for mixed types in fields (D007)."""
        findings: list[Finding] = []

        field_types: dict[str, set[str]] = {}

        for doc in index.sample_documents:
            self._collect_field_types(doc, "", field_types)

        # Find fields with mixed types
        mixed_type_fields = [
            (field, types)
            for field, types in field_types.items()
            if len(types) > 1 and types != {"int", "float"}  # int/float mixing is OK
        ]

        # D007: Mixed types in field
        if mixed_type_fields:
            findings.append(
                Finding(
                    id="MEILI-D007",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Mixed types in fields",
                    description=(
                        f"Fields have inconsistent types across documents: "
                        f"{', '.join(f'{f} ({list(t)})' for f, t in mixed_type_fields[:3])}. "
                        f"This can cause unexpected filtering and sorting behavior."
                    ),
                    impact="Inconsistent filtering and sorting results",
                    index_uid=index.uid,
                    current_value={f: list(t) for f, t in mixed_type_fields[:5]},
                )
            )

        return findings

    def _collect_field_types(
        self, obj: Any, prefix: str, field_types: dict[str, set[str]]
    ) -> None:
        """Collect types for each field."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key

                if value is not None:
                    type_name = type(value).__name__
                    if new_prefix not in field_types:
                        field_types[new_prefix] = set()
                    field_types[new_prefix].add(type_name)

                if isinstance(value, dict):
                    self._collect_field_types(value, new_prefix, field_types)

    def _check_text_length(self, index: IndexData) -> list[Finding]:
        """Check for very long text fields (D008)."""
        findings: list[Finding] = []

        long_text_fields: dict[str, int] = {}

        for doc in index.sample_documents:
            self._find_long_text(doc, "", long_text_fields)

        # D008: Very long text
        if long_text_fields:
            findings.append(
                Finding(
                    id="MEILI-D008",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.SUGGESTION,
                    title="Very long text fields",
                    description=(
                        f"Some fields contain very long text (>65535 chars): "
                        f"{list(long_text_fields.keys())[:3]}. "
                        f"Consider truncating or summarizing for better search performance."
                    ),
                    impact="Potential performance impact on indexing and search",
                    index_uid=index.uid,
                    current_value=long_text_fields,
                )
            )

        return findings

    def _find_long_text(
        self, obj: Any, prefix: str, long_fields: dict[str, int]
    ) -> None:
        """Find fields with very long text."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                self._find_long_text(value, new_prefix, long_fields)
        elif isinstance(obj, str) and len(obj) > 65535:
            long_fields[prefix] = len(obj)
