"""Document analyzer for MeiliSearch index documents."""

import re
from typing import Any

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.index import IndexData


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

    # PII detection patterns
    PII_PATTERNS = {
        "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "phone": re.compile(
            r"(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}"
        ),
        "ssn": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    }

    # Field name patterns that may indicate sensitive data
    SENSITIVE_FIELD_PATTERNS = [
        re.compile(r"(?i)^(email|e_mail|e-mail|mail)$"),
        re.compile(r"(?i)(password|passwd|pwd|secret|token|api_key|apikey)"),
        re.compile(r"(?i)(ssn|social_security|social-security)"),
        re.compile(r"(?i)(credit.?card|card.?number|ccn)"),
        re.compile(r"(?i)(phone|mobile|cell|tel|fax)"),
        re.compile(r"(?i)(address|street|zip|postal|city)"),
        re.compile(r"(?i)(birth.?date|dob|birthday|date.?of.?birth)"),
        re.compile(r"(?i)(driver.?license|passport|national.?id)"),
        re.compile(r"(?i)(salary|income|wage|compensation)"),
        re.compile(r"(?i)(bank|account|routing|iban|swift)"),
    ]

    # Geo coordinate field patterns
    GEO_FIELD_PATTERNS = [
        re.compile(r"(?i)^(lat|latitude)$"),
        re.compile(r"(?i)^(lng|lon|long|longitude)$"),
        re.compile(r"(?i)(location|coordinates?|position|geo)"),
    ]

    # Date/timestamp patterns in strings
    DATE_PATTERNS = [
        # ISO 8601
        re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?"),
        # US format
        re.compile(r"^\d{2}/\d{2}/\d{4}$"),
        # European format
        re.compile(r"^\d{2}-\d{2}-\d{4}$"),
        # Unix timestamp (10 or 13 digits)
        re.compile(r"^\d{10}(\d{3})?$"),
    ]

    # Field names suggesting dates/times
    DATE_FIELD_PATTERNS = [
        re.compile(r"(?i)(created|updated|modified|deleted)_?(at|on|date|time)?$"),
        re.compile(r"(?i)^(date|time|timestamp|datetime)"),
        re.compile(r"(?i)(start|end|begin|finish)_?(date|time)?$"),
        re.compile(r"(?i)(published|posted|submitted)_?(at|on|date)?$"),
        re.compile(r"(?i)_?(date|time|at)$"),
    ]

    @property
    def name(self) -> str:
        return "documents"

    def analyze(
        self, index: IndexData, detect_sensitive: bool = False
    ) -> list[Finding]:
        """Analyze index documents.

        Args:
            index: The index to analyze
            detect_sensitive: Whether to detect PII/sensitive fields

        Returns:
            List of findings
        """
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

        # PII detection (opt-in)
        if detect_sensitive:
            findings.extend(self._check_sensitive_fields(index))
            findings.extend(self._check_pii_content(index))

        # New document checks (D011-D013)
        findings.extend(self._check_arrays_of_objects(index))
        findings.extend(self._check_geo_coordinates(index))
        findings.extend(self._check_date_strings(index))

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
            return max(self._get_max_depth(v, current_depth + 1) for v in obj.values())
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
                        f"{', '.join(f'{f} ({r * 100:.0f}%)' for f, r in high_empty_fields[:3])}. "
                        f"Consider if these fields should be optional or if data quality could be improved."
                    ),
                    impact="Wasted storage, potential search inconsistencies",
                    index_uid=index.uid,
                    current_value={
                        f: f"{r * 100:.0f}%" for f, r in high_empty_fields[:5]
                    },
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
                    self._count_empty_fields(
                        value, new_prefix, empty_counts, total_counts
                    )

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

    def _check_sensitive_fields(self, index: IndexData) -> list[Finding]:
        """Check for field names that suggest sensitive data (D009)."""
        findings: list[Finding] = []

        sensitive_fields: list[str] = []

        # Collect all field names from sample documents
        all_fields: set[str] = set()
        for doc in index.sample_documents:
            self._collect_all_field_names(doc, "", all_fields)

        # Check field names against sensitive patterns
        for field in all_fields:
            field_name = field.split(".")[-1]  # Get the leaf field name
            for pattern in self.SENSITIVE_FIELD_PATTERNS:
                if pattern.search(field_name):
                    sensitive_fields.append(field)
                    break

        # D009: Potentially sensitive field names
        if sensitive_fields:
            findings.append(
                Finding(
                    id="MEILI-D009",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Potentially sensitive field names detected",
                    description=(
                        f"Fields with names suggesting sensitive/PII data: "
                        f"{sensitive_fields[:5]}. "
                        f"Review whether these should be indexed or made searchable. "
                        f"Consider excluding from searchableAttributes or not indexing at all."
                    ),
                    impact="Potential privacy/compliance risk if sensitive data is searchable",
                    index_uid=index.uid,
                    current_value=sensitive_fields[:10],
                    references=[
                        "https://www.meilisearch.com/docs/learn/security/tenant_tokens"
                    ],
                )
            )

        return findings

    def _collect_all_field_names(self, obj: Any, prefix: str, fields: set[str]) -> None:
        """Recursively collect all field names."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                fields.add(new_prefix)
                if isinstance(value, (dict, list)):
                    self._collect_all_field_names(value, new_prefix, fields)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    self._collect_all_field_names(item, prefix, fields)

    def _check_pii_content(self, index: IndexData) -> list[Finding]:
        """Check for PII patterns in field values (D010)."""
        findings: list[Finding] = []

        pii_detections: dict[str, list[str]] = {}

        for doc in index.sample_documents:
            self._scan_for_pii(doc, "", pii_detections)

        # D010: PII patterns in content
        if pii_detections:
            # Format for display
            pii_summary = {
                field: types for field, types in list(pii_detections.items())[:5]
            }

            findings.append(
                Finding(
                    id="MEILI-D010",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.CRITICAL,
                    title="Potential PII detected in document content",
                    description=(
                        f"Fields contain data matching PII patterns: "
                        f"{list(pii_detections.keys())[:5]}. "
                        f"Detected patterns: {set(t for types in pii_detections.values() for t in types)}. "
                        f"This may indicate personally identifiable information that "
                        f"should be masked, excluded, or carefully controlled."
                    ),
                    impact="Privacy/compliance risk, potential data breach exposure",
                    index_uid=index.uid,
                    current_value=pii_summary,
                    references=[
                        "https://www.meilisearch.com/docs/learn/security/tenant_tokens"
                    ],
                )
            )

        return findings

    def _scan_for_pii(
        self, obj: Any, prefix: str, detections: dict[str, list[str]]
    ) -> None:
        """Scan document for PII patterns."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                self._scan_for_pii(value, new_prefix, detections)
        elif isinstance(obj, list):
            for item in obj:
                self._scan_for_pii(item, prefix, detections)
        elif isinstance(obj, str) and len(obj) >= 5:
            # Check string values against PII patterns
            for pii_type, pattern in self.PII_PATTERNS.items():
                if pattern.search(obj):
                    if prefix not in detections:
                        detections[prefix] = []
                    if pii_type not in detections[prefix]:
                        detections[prefix].append(pii_type)

    def _check_arrays_of_objects(self, index: IndexData) -> list[Finding]:
        """Check for arrays of objects that may cause filter/facet issues (D011)."""
        findings: list[Finding] = []

        array_of_objects_fields: dict[str, int] = {}

        for doc in index.sample_documents:
            self._find_arrays_of_objects(doc, "", array_of_objects_fields)

        # D011: Arrays of objects detected
        if array_of_objects_fields:
            # Check if any of these fields are in filterableAttributes
            filterable = set(index.settings.filterable_attributes)
            problematic_fields = []
            info_fields = []

            for field, count in array_of_objects_fields.items():
                # Check if field or parent is filterable
                field_parts = field.split(".")
                is_filterable = any(
                    ".".join(field_parts[: i + 1]) in filterable
                    for i in range(len(field_parts))
                )
                if is_filterable:
                    problematic_fields.append((field, count))
                else:
                    info_fields.append((field, count))

            if problematic_fields:
                findings.append(
                    Finding(
                        id="MEILI-D011",
                        category=FindingCategory.DOCUMENTS,
                        severity=FindingSeverity.WARNING,
                        title="Arrays of objects in filterable fields",
                        description=(
                            f"Filterable fields contain arrays of objects: "
                            f"{[f for f, _ in problematic_fields[:5]]}. "
                            f"MeiliSearch flattens nested arrays, which can cause "
                            f"unexpected filter behavior. Consider restructuring data."
                        ),
                        impact="Filters may not work as expected on nested array fields",
                        index_uid=index.uid,
                        current_value={f: c for f, c in problematic_fields[:5]},
                        references=[
                            "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                        ],
                    )
                )
            elif info_fields:
                # Only report as info if not filterable
                findings.append(
                    Finding(
                        id="MEILI-D011",
                        category=FindingCategory.DOCUMENTS,
                        severity=FindingSeverity.INFO,
                        title="Arrays of objects detected",
                        description=(
                            f"Fields contain arrays of objects: "
                            f"{[f for f, _ in info_fields[:5]]}. "
                            f"MeiliSearch flattens these structures. If you plan to "
                            f"filter on these fields, consider restructuring."
                        ),
                        impact="Nested structure is flattened during indexing",
                        index_uid=index.uid,
                        current_value={f: c for f, c in info_fields[:5]},
                    )
                )

        return findings

    def _find_arrays_of_objects(
        self, obj: Any, prefix: str, results: dict[str, int]
    ) -> None:
        """Find fields that are arrays containing objects."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                self._find_arrays_of_objects(value, new_prefix, results)
        elif isinstance(obj, list) and obj:
            # Check if array contains objects
            has_objects = any(isinstance(item, dict) for item in obj)
            if has_objects:
                results[prefix] = results.get(prefix, 0) + 1
            # Recurse into array items
            for item in obj:
                if isinstance(item, dict):
                    self._find_arrays_of_objects(item, prefix, results)

    def _check_geo_coordinates(self, index: IndexData) -> list[Finding]:
        """Check for geo coordinates that should use _geo format (D012)."""
        findings: list[Finding] = []

        geo_candidates: list[dict[str, Any]] = []

        for doc in index.sample_documents:
            candidates = self._find_geo_candidates(doc)
            if candidates:
                geo_candidates.extend(candidates)

        # Check if _geo field already exists
        has_geo_field = any(
            "_geo" in doc for doc in index.sample_documents if isinstance(doc, dict)
        )

        # D012: Geo coordinates without _geo format
        if geo_candidates and not has_geo_field:
            # Deduplicate by field pattern
            unique_patterns = {}
            for candidate in geo_candidates:
                pattern = candidate.get("pattern", "")
                if pattern not in unique_patterns:
                    unique_patterns[pattern] = candidate

            findings.append(
                Finding(
                    id="MEILI-D012",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.SUGGESTION,
                    title="Potential geo coordinates not using _geo format",
                    description=(
                        f"Fields appear to contain geographic coordinates but "
                        f"are not using the MeiliSearch _geo format: "
                        f"{list(unique_patterns.keys())[:3]}. "
                        f"To enable geo search, restructure to use _geo.lat and _geo.lng."
                    ),
                    impact="Geo search functionality unavailable without _geo format",
                    index_uid=index.uid,
                    current_value=list(unique_patterns.values())[:3],
                    recommended_value={"_geo": {"lat": 45.4773, "lng": -73.6102}},
                    references=[
                        "https://www.meilisearch.com/docs/learn/filtering_and_sorting/geosearch"
                    ],
                )
            )

        return findings

    def _find_geo_candidates(self, doc: dict, prefix: str = "") -> list[dict[str, Any]]:
        """Find fields that look like geo coordinates."""
        candidates = []

        if not isinstance(doc, dict):
            return candidates

        # Look for lat/lng pair patterns
        lat_fields = []
        lng_fields = []

        for key, value in doc.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # Check if field name suggests lat (pattern index 0)
            if self.GEO_FIELD_PATTERNS[0].search(key):
                if isinstance(value, (int, float)) and -90 <= value <= 90:
                    lat_fields.append((full_key, value))

            # Check if field name suggests lng (pattern index 1)
            if self.GEO_FIELD_PATTERNS[1].search(key):
                if isinstance(value, (int, float)) and -180 <= value <= 180:
                    lng_fields.append((full_key, value))

            # Check for nested location objects
            if isinstance(value, dict):
                # Check if this object looks like coordinates
                nested_keys = set(value.keys())
                if {"lat", "lng"}.issubset(nested_keys) or {
                    "latitude",
                    "longitude",
                }.issubset(nested_keys):
                    candidates.append(
                        {
                            "pattern": full_key,
                            "type": "nested_object",
                            "sample": value,
                        }
                    )
                else:
                    # Recurse
                    candidates.extend(self._find_geo_candidates(value, full_key))

        # If we found lat/lng pairs at the same level
        if lat_fields and lng_fields:
            candidates.append(
                {
                    "pattern": f"{lat_fields[0][0]}/{lng_fields[0][0]}",
                    "type": "separate_fields",
                    "lat_field": lat_fields[0][0],
                    "lng_field": lng_fields[0][0],
                }
            )

        return candidates

    def _check_date_strings(self, index: IndexData) -> list[Finding]:
        """Check for date strings that could be sortable numbers (D013)."""
        findings: list[Finding] = []

        date_string_fields: dict[str, list[str]] = {}

        for doc in index.sample_documents:
            self._find_date_strings(doc, "", date_string_fields)

        if not date_string_fields:
            return findings

        # Check which date fields are sortable
        sortable = set(index.settings.sortable_attributes)
        non_sortable_dates = []
        sortable_string_dates = []

        for field, sample_values in date_string_fields.items():
            field_parts = field.split(".")
            is_sortable = any(
                ".".join(field_parts[: i + 1]) in sortable
                for i in range(len(field_parts))
            )

            if is_sortable:
                sortable_string_dates.append((field, sample_values[0]))
            else:
                non_sortable_dates.append((field, sample_values[0]))

        # D013: Date strings that could be numeric for sorting
        if sortable_string_dates:
            findings.append(
                Finding(
                    id="MEILI-D013",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.SUGGESTION,
                    title="Date strings in sortable attributes",
                    description=(
                        f"Sortable fields contain date strings: "
                        f"{[f for f, _ in sortable_string_dates[:3]]}. "
                        f"String dates sort lexicographically, not chronologically. "
                        f"Consider converting to Unix timestamps for proper sorting."
                    ),
                    impact="Date sorting may not work correctly with string formats",
                    index_uid=index.uid,
                    current_value={f: v for f, v in sortable_string_dates[:5]},
                    recommended_value="Unix timestamp (e.g., 1704412800)",
                    references=[
                        "https://www.meilisearch.com/docs/learn/filtering_and_sorting/sort_search_results"
                    ],
                )
            )
        elif non_sortable_dates and len(non_sortable_dates) >= 2:
            # Only suggest if there are multiple date fields not being used
            findings.append(
                Finding(
                    id="MEILI-D013",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.INFO,
                    title="Date fields detected",
                    description=(
                        f"Fields appear to contain dates: "
                        f"{[f for f, _ in non_sortable_dates[:3]]}. "
                        f"If you need to sort by these fields, add them to "
                        f"sortableAttributes and consider using numeric timestamps."
                    ),
                    impact="Date fields not available for sorting",
                    index_uid=index.uid,
                    current_value={f: v for f, v in non_sortable_dates[:5]},
                )
            )

        return findings

    def _find_date_strings(
        self, obj: Any, prefix: str, results: dict[str, list[str]]
    ) -> None:
        """Find string fields that contain date-like values."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key

                if isinstance(value, str) and 8 <= len(value) <= 30:
                    # Check if field name suggests date
                    is_date_field = any(
                        pattern.search(key) for pattern in self.DATE_FIELD_PATTERNS
                    )
                    # Check if value looks like a date
                    is_date_value = any(
                        pattern.match(value) for pattern in self.DATE_PATTERNS
                    )

                    if is_date_field or is_date_value:
                        if new_prefix not in results:
                            results[new_prefix] = []
                        if len(results[new_prefix]) < 2:  # Keep up to 2 samples
                            results[new_prefix].append(value)

                elif isinstance(value, dict):
                    self._find_date_strings(value, new_prefix, results)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            self._find_date_strings(item, new_prefix, results)
