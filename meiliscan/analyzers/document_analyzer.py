"""Document analyzer for MeiliSearch index documents."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.index import IndexData


@dataclass
class DocumentStats:
    """Statistics collected during single-pass document analysis."""

    # Document sizes
    sizes: list[int] = field(default_factory=list)

    # Field occurrences for schema consistency
    field_counts: dict[str, int] = field(default_factory=dict)
    total_docs: int = 0

    # Nesting depth
    max_nesting_depth: int = 0

    # Array statistics: field -> list of sizes
    array_sizes: dict[str, list[int]] = field(default_factory=dict)

    # Fields with markup content
    markup_fields: set[str] = field(default_factory=set)

    # Empty field tracking
    field_empty_counts: dict[str, int] = field(default_factory=dict)
    field_total_counts: dict[str, int] = field(default_factory=dict)

    # Field types for mixed type detection
    field_types: dict[str, set[str]] = field(default_factory=dict)

    # Long text fields
    long_text_fields: dict[str, int] = field(default_factory=dict)

    # Sensitive field names (from field names)
    sensitive_fields: list[str] = field(default_factory=list)

    # PII detections (from content)
    pii_detections: dict[str, list[str]] = field(default_factory=dict)

    # Arrays of objects
    arrays_of_objects: dict[str, int] = field(default_factory=dict)

    # Geo coordinate candidates
    geo_candidates: list[dict[str, Any]] = field(default_factory=list)

    # Date string fields
    date_string_fields: dict[str, list[str]] = field(default_factory=dict)

    # All field names collected
    all_field_names: set[str] = field(default_factory=set)


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
        """Analyze index documents in a single pass.

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

        # Single-pass collection of all statistics
        stats = self._collect_document_stats(
            index.sample_documents, detect_sensitive=detect_sensitive
        )

        # Generate findings from collected stats
        findings.extend(self._findings_from_document_size(stats, index))
        findings.extend(self._findings_from_schema_consistency(stats, index))
        findings.extend(self._findings_from_nesting_depth(stats, index))
        findings.extend(self._findings_from_array_sizes(stats, index))
        findings.extend(self._findings_from_markup_content(stats, index))
        findings.extend(self._findings_from_empty_fields(stats, index))
        findings.extend(self._findings_from_mixed_types(stats, index))
        findings.extend(self._findings_from_text_length(stats, index))

        # PII detection (opt-in)
        if detect_sensitive:
            findings.extend(self._findings_from_sensitive_fields(stats, index))
            findings.extend(self._findings_from_pii_content(stats, index))

        # D011-D013 findings
        findings.extend(self._findings_from_arrays_of_objects(stats, index))
        findings.extend(self._findings_from_geo_coordinates(stats, index))
        findings.extend(self._findings_from_date_strings(stats, index))

        return findings

    def _collect_document_stats(
        self, documents: list[dict[str, Any]], detect_sensitive: bool = False
    ) -> DocumentStats:
        """Collect all statistics in a single pass over documents.

        Args:
            documents: List of sample documents
            detect_sensitive: Whether to scan for PII content

        Returns:
            DocumentStats with all collected statistics
        """
        stats = DocumentStats()
        stats.total_docs = len(documents)

        for doc in documents:
            # Document size
            doc_str = json.dumps(doc)
            stats.sizes.append(len(doc_str.encode("utf-8")))

            # Field counts for schema consistency
            for field_name in doc.keys():
                stats.field_counts[field_name] = (
                    stats.field_counts.get(field_name, 0) + 1
                )

            # Recursively analyze document structure
            self._analyze_document_recursive(
                doc, "", stats, detect_sensitive=detect_sensitive
            )

            # Check for geo candidates
            geo_cands = self._find_geo_candidates(doc)
            if geo_cands:
                stats.geo_candidates.extend(geo_cands)

        # Check sensitive field names against collected field names
        if detect_sensitive:
            for field_name in stats.all_field_names:
                leaf_name = field_name.split(".")[-1]
                for pattern in self.SENSITIVE_FIELD_PATTERNS:
                    if pattern.search(leaf_name):
                        if field_name not in stats.sensitive_fields:
                            stats.sensitive_fields.append(field_name)
                        break

        return stats

    def _analyze_document_recursive(
        self,
        obj: Any,
        prefix: str,
        stats: DocumentStats,
        current_depth: int = 0,
        detect_sensitive: bool = False,
    ) -> None:
        """Recursively analyze a document/value, collecting all statistics.

        Args:
            obj: Current object/value to analyze
            prefix: Current field path prefix
            stats: Statistics collector
            current_depth: Current nesting depth
            detect_sensitive: Whether to scan for PII
        """
        if isinstance(obj, dict):
            # Update max nesting depth
            if current_depth > stats.max_nesting_depth:
                stats.max_nesting_depth = current_depth

            for key, value in obj.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                stats.all_field_names.add(new_prefix)

                # Track field total counts and empty values
                stats.field_total_counts[new_prefix] = (
                    stats.field_total_counts.get(new_prefix, 0) + 1
                )

                if value is None or value == "" or value == [] or value == {}:
                    stats.field_empty_counts[new_prefix] = (
                        stats.field_empty_counts.get(new_prefix, 0) + 1
                    )

                # Track field types (excluding None)
                if value is not None:
                    type_name = type(value).__name__
                    if new_prefix not in stats.field_types:
                        stats.field_types[new_prefix] = set()
                    stats.field_types[new_prefix].add(type_name)

                # Recurse into nested structures
                if isinstance(value, (dict, list)):
                    self._analyze_document_recursive(
                        value,
                        new_prefix,
                        stats,
                        current_depth + 1,
                        detect_sensitive,
                    )
                elif isinstance(value, str):
                    self._analyze_string_value(
                        value, new_prefix, key, stats, detect_sensitive
                    )

        elif isinstance(obj, list):
            if prefix:
                # Track array sizes
                if prefix not in stats.array_sizes:
                    stats.array_sizes[prefix] = []
                stats.array_sizes[prefix].append(len(obj))

                # Check if array contains objects
                has_objects = any(isinstance(item, dict) for item in obj)
                if has_objects:
                    stats.arrays_of_objects[prefix] = (
                        stats.arrays_of_objects.get(prefix, 0) + 1
                    )

            # Recurse into array items
            for item in obj:
                if isinstance(item, (dict, list)):
                    self._analyze_document_recursive(
                        item, prefix, stats, current_depth, detect_sensitive
                    )
                elif isinstance(item, str):
                    self._analyze_string_value(
                        item, prefix, "", stats, detect_sensitive
                    )

    def _analyze_string_value(
        self,
        value: str,
        prefix: str,
        key: str,
        stats: DocumentStats,
        detect_sensitive: bool,
    ) -> None:
        """Analyze a string value for markup, PII, dates, and length.

        Args:
            value: String value to analyze
            prefix: Full field path
            key: Field key name
            stats: Statistics collector
            detect_sensitive: Whether to scan for PII
        """
        str_len = len(value)

        # Check for very long text (D008)
        if str_len > 65535:
            stats.long_text_fields[prefix] = str_len

        # Check for markup (D005) - only for strings > 10 chars
        if str_len > 10 and prefix not in stats.markup_fields:
            for pattern in self.MARKUP_PATTERNS:
                if pattern.search(value):
                    stats.markup_fields.add(prefix)
                    break

        # Check for PII content (D010) - only if enabled
        if detect_sensitive and str_len >= 5:
            for pii_type, pattern in self.PII_PATTERNS.items():
                if pattern.search(value):
                    if prefix not in stats.pii_detections:
                        stats.pii_detections[prefix] = []
                    if pii_type not in stats.pii_detections[prefix]:
                        stats.pii_detections[prefix].append(pii_type)

        # Check for date strings (D013) - only for appropriate length strings
        if 8 <= str_len <= 30:
            # Check if field name suggests date
            is_date_field = any(
                pattern.search(key) for pattern in self.DATE_FIELD_PATTERNS
            )
            # Check if value looks like a date
            is_date_value = any(pattern.match(value) for pattern in self.DATE_PATTERNS)

            if is_date_field or is_date_value:
                if prefix not in stats.date_string_fields:
                    stats.date_string_fields[prefix] = []
                if len(stats.date_string_fields[prefix]) < 2:  # Keep up to 2 samples
                    stats.date_string_fields[prefix].append(value)

    def _find_geo_candidates(self, doc: dict, prefix: str = "") -> list[dict[str, Any]]:
        """Find fields that look like geo coordinates."""
        candidates = []

        if not isinstance(doc, dict):
            return candidates

        lat_fields = []
        lng_fields = []

        for key, value in doc.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # Check if field name suggests lat
            if self.GEO_FIELD_PATTERNS[0].search(key):
                if isinstance(value, (int, float)) and -90 <= value <= 90:
                    lat_fields.append((full_key, value))

            # Check if field name suggests lng
            if self.GEO_FIELD_PATTERNS[1].search(key):
                if isinstance(value, (int, float)) and -180 <= value <= 180:
                    lng_fields.append((full_key, value))

            # Check for nested location objects
            if isinstance(value, dict):
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

    # --- Finding generation methods (from collected stats) ---

    def _findings_from_document_size(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D001 finding from collected size stats."""
        findings: list[Finding] = []

        if not stats.sizes:
            return findings

        avg_size = sum(stats.sizes) / len(stats.sizes)
        max_size = max(stats.sizes)

        if avg_size > 10 * 1024 or max_size > 100 * 1024:
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

    def _findings_from_schema_consistency(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D002 finding from field count stats."""
        findings: list[Finding] = []

        if stats.total_docs < 10:
            return findings

        inconsistent_fields = [
            field
            for field, count in stats.field_counts.items()
            if count < stats.total_docs * 0.8 and count > stats.total_docs * 0.2
        ]

        if inconsistent_fields:
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

    def _findings_from_nesting_depth(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D003 finding from nesting depth stats."""
        findings: list[Finding] = []

        if stats.max_nesting_depth > 3:
            findings.append(
                Finding(
                    id="MEILI-D003",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Deep document nesting",
                    description=(
                        f"Documents have nesting depth of {stats.max_nesting_depth}. "
                        f"MeiliSearch flattens nested objects, which can lead to "
                        f"unexpected field names and search behavior."
                    ),
                    impact="Flattened field names, potential search issues",
                    index_uid=index.uid,
                    current_value=stats.max_nesting_depth,
                    recommended_value=3,
                    references=[
                        "https://www.meilisearch.com/docs/learn/indexing/indexing_best_practices"
                    ],
                )
            )

        return findings

    def _findings_from_array_sizes(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D004 finding from array size stats."""
        findings: list[Finding] = []

        large_arrays = []
        for field_name, sizes in stats.array_sizes.items():
            if sizes:
                avg_size = sum(sizes) / len(sizes)
                if avg_size > 50:
                    large_arrays.append((field_name, avg_size))

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

    def _findings_from_markup_content(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D005 finding from markup detection stats."""
        findings: list[Finding] = []

        if stats.markup_fields:
            findings.append(
                Finding(
                    id="MEILI-D005",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.SUGGESTION,
                    title="HTML/Markdown content in text fields",
                    description=(
                        f"Fields contain HTML or Markdown markup: {list(stats.markup_fields)[:5]}. "
                        f"Consider stripping markup before indexing for better search results."
                    ),
                    impact="Markup tags may appear in search results",
                    index_uid=index.uid,
                    current_value=list(stats.markup_fields)[:10],
                )
            )

        return findings

    def _findings_from_empty_fields(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D006 finding from empty field stats."""
        findings: list[Finding] = []

        high_empty_fields = []
        for field_name, empty_count in stats.field_empty_counts.items():
            total = stats.field_total_counts.get(field_name, 0)
            if total > 0:
                ratio = empty_count / total
                if ratio > 0.3:
                    high_empty_fields.append((field_name, ratio))

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

    def _findings_from_mixed_types(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D007 finding from field type stats."""
        findings: list[Finding] = []

        mixed_type_fields = [
            (field, types)
            for field, types in stats.field_types.items()
            if len(types) > 1 and types != {"int", "float"}
        ]

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

    def _findings_from_text_length(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D008 finding from long text stats."""
        findings: list[Finding] = []

        if stats.long_text_fields:
            findings.append(
                Finding(
                    id="MEILI-D008",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.SUGGESTION,
                    title="Very long text fields",
                    description=(
                        f"Some fields contain very long text (>65535 chars): "
                        f"{list(stats.long_text_fields.keys())[:3]}. "
                        f"Consider truncating or summarizing for better search performance."
                    ),
                    impact="Potential performance impact on indexing and search",
                    index_uid=index.uid,
                    current_value=stats.long_text_fields,
                )
            )

        return findings

    def _findings_from_sensitive_fields(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D009 finding from sensitive field name detection."""
        findings: list[Finding] = []

        if stats.sensitive_fields:
            findings.append(
                Finding(
                    id="MEILI-D009",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.WARNING,
                    title="Potentially sensitive field names detected",
                    description=(
                        f"Fields with names suggesting sensitive/PII data: "
                        f"{stats.sensitive_fields[:5]}. "
                        f"Review whether these should be indexed or made searchable. "
                        f"Consider excluding from searchableAttributes or not indexing at all."
                    ),
                    impact="Potential privacy/compliance risk if sensitive data is searchable",
                    index_uid=index.uid,
                    current_value=stats.sensitive_fields[:10],
                    references=[
                        "https://www.meilisearch.com/docs/learn/security/tenant_tokens"
                    ],
                )
            )

        return findings

    def _findings_from_pii_content(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D010 finding from PII content detection."""
        findings: list[Finding] = []

        if stats.pii_detections:
            pii_summary = {
                field: types for field, types in list(stats.pii_detections.items())[:5]
            }

            findings.append(
                Finding(
                    id="MEILI-D010",
                    category=FindingCategory.DOCUMENTS,
                    severity=FindingSeverity.CRITICAL,
                    title="Potential PII detected in document content",
                    description=(
                        f"Fields contain data matching PII patterns: "
                        f"{list(stats.pii_detections.keys())[:5]}. "
                        f"Detected patterns: {set(t for types in stats.pii_detections.values() for t in types)}. "
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

    def _findings_from_arrays_of_objects(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D011 finding from arrays of objects detection."""
        findings: list[Finding] = []

        if not stats.arrays_of_objects:
            return findings

        filterable = set(index.settings.filterable_attributes)
        problematic_fields = []
        info_fields = []

        for field_name, count in stats.arrays_of_objects.items():
            field_parts = field_name.split(".")
            is_filterable = any(
                ".".join(field_parts[: i + 1]) in filterable
                for i in range(len(field_parts))
            )
            if is_filterable:
                problematic_fields.append((field_name, count))
            else:
                info_fields.append((field_name, count))

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

    def _findings_from_geo_coordinates(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D012 finding from geo coordinate detection."""
        findings: list[Finding] = []

        if not stats.geo_candidates:
            return findings

        # Check if _geo field already exists
        has_geo_field = "_geo" in stats.all_field_names

        if not has_geo_field:
            unique_patterns = {}
            for candidate in stats.geo_candidates:
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

    def _findings_from_date_strings(
        self, stats: DocumentStats, index: IndexData
    ) -> list[Finding]:
        """Generate D013 finding from date string detection."""
        findings: list[Finding] = []

        if not stats.date_string_fields:
            return findings

        sortable = set(index.settings.sortable_attributes)
        non_sortable_dates = []
        sortable_string_dates = []

        for field_name, sample_values in stats.date_string_fields.items():
            field_parts = field_name.split(".")
            is_sortable = any(
                ".".join(field_parts[: i + 1]) in sortable
                for i in range(len(field_parts))
            )

            if is_sortable:
                sortable_string_dates.append((field_name, sample_values[0]))
            else:
                non_sortable_dates.append((field_name, sample_values[0]))

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
