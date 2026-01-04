"""Schema analyzer for MeiliSearch index settings."""

import re

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingFix,
    FindingSeverity,
)
from meiliscan.models.index import IndexData


class SchemaAnalyzer(BaseAnalyzer):
    """Analyzer for index schema and settings."""

    # Default MeiliSearch ranking rules
    DEFAULT_RANKING_RULES = [
        "words",
        "typo",
        "proximity",
        "attribute",
        "sort",
        "exactness",
    ]

    # Common ID field patterns
    ID_PATTERNS = [
        r"^id$",
        r"^_id$",
        r".*_id$",
        r".*Id$",
        r".*ID$",
        r"^uuid$",
        r"^guid$",
    ]

    # Common mutable/non-identifier field names (not suitable as primary key)
    MUTABLE_FIELD_PATTERNS = [
        r"^title$",
        r"^name$",
        r"^label$",
        r"^description$",
        r"^content$",
        r"^text$",
        r"^body$",
        r"^status$",
        r"^state$",
        r"^email$",
        r"^url$",
        r"^slug$",
    ]

    # Common sort field candidates
    SORT_CANDIDATE_PATTERNS = [
        r".*created.*",
        r".*updated.*",
        r".*date.*",
        r".*time.*",
        r".*price.*",
        r".*rating.*",
        r".*score.*",
        r".*rank.*",
        r".*order.*",
        r".*priority.*",
        r".*popularity.*",
        r".*views?$",
        r".*count$",
    ]

    # High-cardinality patterns (not good for filtering/faceting)
    HIGH_CARDINALITY_PATTERNS = [
        r".*email.*",
        r".*uuid.*",
        r".*guid.*",
        r".*token.*",
        r".*hash.*",
        r".*key$",
        r".*_id$",
        r"^id$",
        r".*url.*",
        r".*path.*",
        r".*slug.*",
    ]

    @property
    def name(self) -> str:
        return "schema"

    def analyze(self, index: IndexData) -> list[Finding]:
        """Analyze index schema and settings."""
        findings: list[Finding] = []

        # Existing checks (S001-S010)
        findings.extend(self._check_searchable_attributes(index))
        findings.extend(self._check_filterable_attributes(index))
        findings.extend(self._check_sortable_attributes(index))
        findings.extend(self._check_displayed_attributes(index))
        findings.extend(self._check_ranking_rules(index))
        findings.extend(self._check_stop_words(index))
        findings.extend(self._check_distinct_attribute(index))
        findings.extend(self._check_pagination_settings(index))
        findings.extend(self._check_typo_tolerance(index))

        # New checks (S011-S020)
        findings.extend(self._check_primary_key(index))
        findings.extend(self._check_sortable_types(index))
        findings.extend(self._check_filterable_cardinality(index))
        findings.extend(self._check_faceting_settings(index))
        findings.extend(self._check_synonyms(index))
        findings.extend(self._check_dictionary_settings(index))

        return findings

    def _check_searchable_attributes(self, index: IndexData) -> list[Finding]:
        """Check searchable attributes configuration (S001-S003)."""
        findings: list[Finding] = []
        settings = index.settings
        searchable = settings.searchable_attributes

        # S001: Wildcard searchableAttributes
        if searchable == ["*"]:
            # Suggest fields based on field distribution (exclude likely ID fields)
            suggested_fields = [
                field
                for field in index.stats.field_distribution.keys()
                if not self._is_id_field(field)
                and not self._is_likely_numeric_only(field, index)
            ][:10]  # Limit to 10 suggestions

            findings.append(
                Finding(
                    id="MEILI-S001",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Wildcard searchableAttributes",
                    description=(
                        "searchableAttributes is set to ['*'], causing all fields including "
                        "IDs and numbers to be indexed for search. This increases index size "
                        "and may return irrelevant results."
                    ),
                    impact="Increased index size, slower indexing, potentially irrelevant search results",
                    index_uid=index.uid,
                    current_value=["*"],
                    recommended_value=suggested_fields if suggested_fields else None,
                    fix=FindingFix(
                        type="settings_update",
                        endpoint=f"PATCH /indexes/{index.uid}/settings",
                        payload={"searchableAttributes": suggested_fields}
                        if suggested_fields
                        else {},
                    ),
                    references=[
                        "https://www.meilisearch.com/docs/learn/relevancy/displayed_searchable_attributes"
                    ],
                )
            )
        else:
            # S002: ID fields in searchableAttributes
            id_fields_in_searchable = [f for f in searchable if self._is_id_field(f)]
            if id_fields_in_searchable:
                recommended = [
                    f for f in searchable if f not in id_fields_in_searchable
                ]
                findings.append(
                    Finding(
                        id="MEILI-S002",
                        category=FindingCategory.SCHEMA,
                        severity=FindingSeverity.WARNING,
                        title="ID fields in searchableAttributes",
                        description=(
                            f"Fields that appear to be identifiers are included in searchableAttributes: "
                            f"{id_fields_in_searchable}. Users typically don't search for IDs."
                        ),
                        impact="Wasted index space, potential for irrelevant search results",
                        index_uid=index.uid,
                        current_value=searchable,
                        recommended_value=recommended,
                        fix=FindingFix(
                            type="settings_update",
                            endpoint=f"PATCH /indexes/{index.uid}/settings",
                            payload={"searchableAttributes": recommended},
                        ),
                        references=[
                            "https://www.meilisearch.com/docs/learn/relevancy/displayed_searchable_attributes"
                        ],
                    )
                )

            # S003: Numeric fields in searchableAttributes
            numeric_fields = [
                f
                for f in searchable
                if self._is_likely_numeric_only(f, index)
                and f not in id_fields_in_searchable
            ]
            if numeric_fields:
                findings.append(
                    Finding(
                        id="MEILI-S003",
                        category=FindingCategory.SCHEMA,
                        severity=FindingSeverity.SUGGESTION,
                        title="Numeric fields in searchableAttributes",
                        description=(
                            f"Fields that appear to be numeric are in searchableAttributes: {numeric_fields}. "
                            "Consider if these should be filterable instead of searchable."
                        ),
                        impact="May not match user search intent",
                        index_uid=index.uid,
                        current_value=numeric_fields,
                        references=[
                            "https://www.meilisearch.com/docs/learn/filtering_and_sorting/filter_search_results"
                        ],
                    )
                )

        return findings

    def _check_filterable_attributes(self, index: IndexData) -> list[Finding]:
        """Check filterable attributes configuration (S004-S005)."""
        findings: list[Finding] = []
        settings = index.settings
        filterable = settings.filterable_attributes

        # S004: Empty filterableAttributes
        if not filterable:
            # Suggest fields that might be good for filtering
            suggested = self._suggest_filterable_fields(index)
            findings.append(
                Finding(
                    id="MEILI-S004",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.INFO,
                    title="No filterable attributes configured",
                    description=(
                        "No filterable attributes are configured. If you need to filter or facet "
                        "search results, you'll need to configure filterableAttributes."
                    ),
                    impact="Cannot use filters in search queries",
                    index_uid=index.uid,
                    current_value=[],
                    recommended_value=suggested if suggested else None,
                    references=[
                        "https://www.meilisearch.com/docs/learn/filtering_and_sorting/filter_search_results"
                    ],
                )
            )

        return findings

    def _check_sortable_attributes(self, index: IndexData) -> list[Finding]:
        """Check sortable attributes configuration (S013)."""
        findings: list[Finding] = []
        settings = index.settings
        sortable = settings.sortable_attributes

        # S013: No sortable attributes but has common sort candidates
        if not sortable:
            sort_candidates = self._find_sort_candidates(index)
            if sort_candidates:
                findings.append(
                    Finding(
                        id="MEILI-S013",
                        category=FindingCategory.SCHEMA,
                        severity=FindingSeverity.INFO,
                        title="No sortable attributes configured",
                        description=(
                            f"No sortable attributes are configured, but the index contains "
                            f"fields that are commonly used for sorting: {sort_candidates[:5]}. "
                            f"Consider adding these to sortableAttributes if you need to sort results."
                        ),
                        impact="Cannot sort search results by these fields",
                        index_uid=index.uid,
                        current_value=[],
                        recommended_value=sort_candidates[:5],
                        references=[
                            "https://www.meilisearch.com/docs/learn/filtering_and_sorting/sort_search_results"
                        ],
                    )
                )

        return findings

    def _check_displayed_attributes(self, index: IndexData) -> list[Finding]:
        """Check displayed attributes configuration."""
        findings: list[Finding] = []
        settings = index.settings
        displayed = settings.displayed_attributes

        # Check for wildcard with large documents
        if displayed == ["*"] and index.field_count > 20:
            findings.append(
                Finding(
                    id="MEILI-S005",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="Wildcard displayedAttributes with many fields",
                    description=(
                        f"displayedAttributes is ['*'] but the index has {index.field_count} fields. "
                        "Consider specifying only the fields you need to return in search results."
                    ),
                    impact="Larger response payloads, increased bandwidth usage",
                    index_uid=index.uid,
                    current_value=["*"],
                    references=[
                        "https://www.meilisearch.com/docs/learn/relevancy/displayed_searchable_attributes"
                    ],
                )
            )

        return findings

    def _check_ranking_rules(self, index: IndexData) -> list[Finding]:
        """Check ranking rules configuration (S007)."""
        findings: list[Finding] = []
        settings = index.settings
        ranking_rules = settings.ranking_rules

        # S007: Default ranking rules
        if ranking_rules == self.DEFAULT_RANKING_RULES:
            findings.append(
                Finding(
                    id="MEILI-S007",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.INFO,
                    title="Default ranking rules",
                    description=(
                        "Using default ranking rules. Consider customizing for your specific use case "
                        "if search relevancy isn't meeting expectations."
                    ),
                    impact="May not be optimal for your specific search use case",
                    index_uid=index.uid,
                    current_value=ranking_rules,
                    references=[
                        "https://www.meilisearch.com/docs/learn/relevancy/relevancy"
                    ],
                )
            )

        return findings

    def _check_stop_words(self, index: IndexData) -> list[Finding]:
        """Check stop words configuration (S006)."""
        findings: list[Finding] = []
        settings = index.settings
        stop_words = settings.stop_words

        # S006: Missing stop words
        if not stop_words and index.document_count > 100:
            findings.append(
                Finding(
                    id="MEILI-S006",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="No stop words configured",
                    description=(
                        "No stop words are configured. Adding language-appropriate stop words "
                        "can improve search relevancy by ignoring common words like 'the', 'a', 'is'."
                    ),
                    impact="Common words may affect search ranking unnecessarily",
                    index_uid=index.uid,
                    current_value=[],
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#stop-words"
                    ],
                )
            )

        return findings

    def _check_distinct_attribute(self, index: IndexData) -> list[Finding]:
        """Check distinct attribute configuration (S008)."""
        findings: list[Finding] = []
        settings = index.settings

        # S008: No distinct attribute
        if settings.distinct_attribute is None and index.document_count > 1000:
            findings.append(
                Finding(
                    id="MEILI-S008",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="No distinct attribute set",
                    description=(
                        "No distinct attribute is configured. If your documents may have "
                        "near-duplicates, consider setting a distinct attribute to avoid "
                        "showing similar results."
                    ),
                    impact="Potentially duplicate or very similar results in search",
                    index_uid=index.uid,
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#distinct-attribute"
                    ],
                )
            )

        return findings

    def _check_pagination_settings(self, index: IndexData) -> list[Finding]:
        """Check pagination settings (S009-S010)."""
        findings: list[Finding] = []
        settings = index.settings
        max_hits = settings.pagination.max_total_hits

        # S009: Low pagination limit
        if max_hits < 100:
            findings.append(
                Finding(
                    id="MEILI-S009",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.WARNING,
                    title="Very low pagination limit",
                    description=(
                        f"maxTotalHits is set to {max_hits}, which limits the total results "
                        "accessible through pagination. This may prevent users from accessing "
                        "all relevant results."
                    ),
                    impact="Users cannot paginate beyond the limit",
                    index_uid=index.uid,
                    current_value=max_hits,
                    recommended_value=1000,
                    fix=FindingFix(
                        type="settings_update",
                        endpoint=f"PATCH /indexes/{index.uid}/settings",
                        payload={"pagination": {"maxTotalHits": 1000}},
                    ),
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#pagination"
                    ],
                )
            )

        # S010: High pagination limit
        elif max_hits > 10000:
            findings.append(
                Finding(
                    id="MEILI-S010",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="High pagination limit",
                    description=(
                        f"maxTotalHits is set to {max_hits}. Very high limits can impact "
                        "performance. Consider if users really need to paginate that far."
                    ),
                    impact="Potential performance impact on deep pagination",
                    index_uid=index.uid,
                    current_value=max_hits,
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#pagination"
                    ],
                )
            )

        return findings

    def _check_typo_tolerance(self, index: IndexData) -> list[Finding]:
        """Check typo tolerance settings (S018-S019)."""
        findings: list[Finding] = []
        settings = index.settings
        typo_tolerance = settings.typo_tolerance

        if not typo_tolerance.enabled:
            return findings

        # S018: Typo tolerance enabled on identifier-heavy indexes
        searchable = settings.searchable_attributes
        if searchable != ["*"]:
            id_fields_searchable = [f for f in searchable if self._is_id_field(f)]
            disabled_fields = typo_tolerance.disable_on_attributes

            # Check if ID fields are searchable but not in disableOnAttributes
            unprotected_id_fields = [
                f for f in id_fields_searchable if f not in disabled_fields
            ]

            if unprotected_id_fields:
                findings.append(
                    Finding(
                        id="MEILI-S018",
                        category=FindingCategory.SCHEMA,
                        severity=FindingSeverity.SUGGESTION,
                        title="Typo tolerance enabled on ID-like fields",
                        description=(
                            f"Typo tolerance is enabled for ID-like fields: {unprotected_id_fields}. "
                            f"Typos in identifier searches rarely help users. Consider adding these "
                            f"fields to disableOnAttributes."
                        ),
                        impact="Typo tolerance on IDs may return unexpected results",
                        index_uid=index.uid,
                        current_value={"disableOnAttributes": disabled_fields},
                        recommended_value={
                            "disableOnAttributes": list(
                                set(disabled_fields + unprotected_id_fields)
                            )
                        },
                        fix=FindingFix(
                            type="settings_update",
                            endpoint=f"PATCH /indexes/{index.uid}/settings",
                            payload={
                                "typoTolerance": {
                                    "disableOnAttributes": list(
                                        set(disabled_fields + unprotected_id_fields)
                                    )
                                }
                            },
                        ),
                        references=[
                            "https://www.meilisearch.com/docs/reference/api/settings#typo-tolerance"
                        ],
                    )
                )

        # S019: Extremely permissive minWordSizeForTypos
        min_sizes = typo_tolerance.min_word_size_for_typos
        one_typo = min_sizes.get("oneTypo", 5)
        two_typos = min_sizes.get("twoTypos", 9)

        if one_typo < 3 or two_typos < 5:
            findings.append(
                Finding(
                    id="MEILI-S019",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.INFO,
                    title="Very permissive typo tolerance settings",
                    description=(
                        f"minWordSizeForTypos is set to very low values (oneTypo: {one_typo}, "
                        f"twoTypos: {two_typos}). This allows typos in very short words, which "
                        f"may lead to unexpected matches."
                    ),
                    impact="Very short words will match with typos, potentially reducing relevancy",
                    index_uid=index.uid,
                    current_value=min_sizes,
                    recommended_value={"oneTypo": 5, "twoTypos": 9},
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#typo-tolerance"
                    ],
                )
            )

        return findings

    def _is_id_field(self, field_name: str) -> bool:
        """Check if a field name appears to be an ID field."""
        for pattern in self.ID_PATTERNS:
            if re.match(pattern, field_name, re.IGNORECASE):
                return True
        return False

    def _is_likely_numeric_only(self, field_name: str, index: IndexData) -> bool:
        """Check if a field is likely to contain only numeric values."""
        # Common numeric field name patterns
        numeric_patterns = [
            r".*price.*",
            r".*amount.*",
            r".*quantity.*",
            r".*count.*",
            r".*total.*",
            r".*score.*",
            r".*rating.*",
            r".*age.*",
            r".*year.*",
            r".*number.*",
        ]

        for pattern in numeric_patterns:
            if re.match(pattern, field_name, re.IGNORECASE):
                return True

        # Check sample documents if available
        if index.sample_documents:
            values = [
                doc.get(field_name)
                for doc in index.sample_documents
                if field_name in doc
            ]
            if values and all(
                isinstance(v, (int, float)) for v in values if v is not None
            ):
                return True

        return False

    def _suggest_filterable_fields(self, index: IndexData) -> list[str]:
        """Suggest fields that might be good for filtering."""
        suggestions = []

        # Common filterable field patterns
        filterable_patterns = [
            r".*category.*",
            r".*type.*",
            r".*status.*",
            r".*brand.*",
            r".*color.*",
            r".*size.*",
            r".*tag.*",
            r".*genre.*",
        ]

        for field in index.stats.field_distribution.keys():
            for pattern in filterable_patterns:
                if re.match(pattern, field, re.IGNORECASE):
                    suggestions.append(field)
                    break

        return suggestions[:5]  # Limit suggestions

    def _check_primary_key(self, index: IndexData) -> list[Finding]:
        """Check primary key configuration (S011-S012)."""
        findings: list[Finding] = []

        # S011: Index has no primaryKey
        if index.primary_key is None:
            findings.append(
                Finding(
                    id="MEILI-S011",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.CRITICAL,
                    title="Index has no primary key",
                    description=(
                        "The index does not have a primary key defined. MeiliSearch will "
                        "auto-detect the primary key from the first document, but this can "
                        "lead to unexpected behavior if documents have different structures."
                    ),
                    impact="Risk of inconsistent document identification and potential indexing failures",
                    index_uid=index.uid,
                    current_value=None,
                    references=[
                        "https://www.meilisearch.com/docs/learn/getting_started/primary_key"
                    ],
                )
            )
        else:
            # S012: Primary key looks mutable/non-identifier
            for pattern in self.MUTABLE_FIELD_PATTERNS:
                if re.match(pattern, index.primary_key, re.IGNORECASE):
                    findings.append(
                        Finding(
                            id="MEILI-S012",
                            category=FindingCategory.SCHEMA,
                            severity=FindingSeverity.WARNING,
                            title="Primary key appears to be a mutable field",
                            description=(
                                f"The primary key '{index.primary_key}' looks like a mutable or "
                                f"non-identifier field. Primary keys should be unique, immutable "
                                f"identifiers (like 'id', 'uuid', or '*_id')."
                            ),
                            impact="Document updates may fail or create duplicates if this field changes",
                            index_uid=index.uid,
                            current_value=index.primary_key,
                            recommended_value="id",
                            references=[
                                "https://www.meilisearch.com/docs/learn/getting_started/primary_key"
                            ],
                        )
                    )
                    break

            # Also check if primary key field exists in sample documents
            if index.sample_documents:
                missing_pk_count = sum(
                    1 for doc in index.sample_documents if index.primary_key not in doc
                )
                if missing_pk_count > 0:
                    findings.append(
                        Finding(
                            id="MEILI-S011",
                            category=FindingCategory.SCHEMA,
                            severity=FindingSeverity.CRITICAL,
                            title="Primary key field missing from documents",
                            description=(
                                f"The primary key field '{index.primary_key}' is missing from "
                                f"{missing_pk_count} of {len(index.sample_documents)} sampled documents. "
                                f"This will cause indexing failures for those documents."
                            ),
                            impact="Documents without the primary key field will fail to index",
                            index_uid=index.uid,
                            current_value=f"{missing_pk_count}/{len(index.sample_documents)} missing",
                            references=[
                                "https://www.meilisearch.com/docs/learn/getting_started/primary_key"
                            ],
                        )
                    )

        return findings

    def _find_sort_candidates(self, index: IndexData) -> list[str]:
        """Find fields that are commonly used for sorting."""
        candidates = []
        fields = list(index.stats.field_distribution.keys())

        for field in fields:
            for pattern in self.SORT_CANDIDATE_PATTERNS:
                if re.match(pattern, field, re.IGNORECASE):
                    candidates.append(field)
                    break

        return candidates

    def _check_sortable_types(self, index: IndexData) -> list[Finding]:
        """Check sortable attribute types (S014)."""
        findings: list[Finding] = []
        settings = index.settings
        sortable = settings.sortable_attributes

        if not sortable or not index.sample_documents:
            return findings

        # S014: Check for inconsistent types in sortable attributes
        for field in sortable:
            types_found: set[str] = set()
            for doc in index.sample_documents:
                if field in doc:
                    value = doc[field]
                    if value is None:
                        types_found.add("null")
                    elif isinstance(value, bool):
                        types_found.add("boolean")
                    elif isinstance(value, int):
                        types_found.add("integer")
                    elif isinstance(value, float):
                        types_found.add("float")
                    elif isinstance(value, str):
                        types_found.add("string")
                    elif isinstance(value, list):
                        types_found.add("array")
                    elif isinstance(value, dict):
                        types_found.add("object")

            # Check for problematic type combinations
            # Mixing numeric and string types is problematic for sorting
            has_numeric = bool(types_found & {"integer", "float"})
            has_string = "string" in types_found
            has_complex = bool(types_found & {"array", "object"})

            if has_complex:
                findings.append(
                    Finding(
                        id="MEILI-S014",
                        category=FindingCategory.SCHEMA,
                        severity=FindingSeverity.WARNING,
                        title="Sortable attribute contains complex types",
                        description=(
                            f"The sortable attribute '{field}' contains array or object values "
                            f"in sample documents. Sorting on complex types may not work as expected."
                        ),
                        impact="Sorting may produce unexpected or inconsistent results",
                        index_uid=index.uid,
                        current_value={
                            "field": field,
                            "types_found": list(types_found),
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/filtering_and_sorting/sort_search_results"
                        ],
                    )
                )
            elif has_numeric and has_string:
                findings.append(
                    Finding(
                        id="MEILI-S014",
                        category=FindingCategory.SCHEMA,
                        severity=FindingSeverity.WARNING,
                        title="Sortable attribute has inconsistent types",
                        description=(
                            f"The sortable attribute '{field}' contains both numeric and string values "
                            f"across sample documents. Types found: {sorted(types_found)}. "
                            f"This may cause inconsistent sort behavior."
                        ),
                        impact="Mixed types can lead to unpredictable sort ordering",
                        index_uid=index.uid,
                        current_value={
                            "field": field,
                            "types_found": list(types_found),
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/filtering_and_sorting/sort_search_results"
                        ],
                    )
                )

        return findings

    def _check_filterable_cardinality(self, index: IndexData) -> list[Finding]:
        """Check for high-cardinality filterable attributes (S015)."""
        findings: list[Finding] = []
        settings = index.settings
        filterable = settings.filterable_attributes

        if not filterable:
            return findings

        # S015: Check for high-cardinality patterns in filterable attributes
        high_cardinality_fields = []
        for field in filterable:
            for pattern in self.HIGH_CARDINALITY_PATTERNS:
                if re.match(pattern, field, re.IGNORECASE):
                    high_cardinality_fields.append(field)
                    break

        # Also check sample documents for unique value ratio
        if index.sample_documents:
            for field in filterable:
                if field in high_cardinality_fields:
                    continue  # Already flagged by pattern

                values = [
                    doc.get(field)
                    for doc in index.sample_documents
                    if field in doc and doc.get(field) is not None
                ]
                if len(values) >= 5:
                    unique_values = len(set(str(v) for v in values))
                    # If almost all values are unique, it's likely high-cardinality
                    if unique_values >= len(values) * 0.9:
                        high_cardinality_fields.append(field)

        if high_cardinality_fields:
            findings.append(
                Finding(
                    id="MEILI-S015",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="High-cardinality filterable attributes detected",
                    description=(
                        f"The following filterable attributes appear to be high-cardinality "
                        f"(many unique values): {high_cardinality_fields}. High-cardinality "
                        f"fields are generally not good candidates for filtering or faceting."
                    ),
                    impact="May increase memory usage and reduce filter/facet performance",
                    index_uid=index.uid,
                    current_value=high_cardinality_fields,
                    references=[
                        "https://www.meilisearch.com/docs/learn/filtering_and_sorting/filter_search_results"
                    ],
                )
            )

        return findings

    def _check_faceting_settings(self, index: IndexData) -> list[Finding]:
        """Check faceting configuration (S016)."""
        findings: list[Finding] = []
        settings = index.settings
        max_values = settings.faceting.max_values_per_facet

        if not settings.filterable_attributes:
            return findings

        # S016: Check maxValuesPerFacet against observed values
        if index.sample_documents:
            for field in settings.filterable_attributes:
                values = [
                    doc.get(field)
                    for doc in index.sample_documents
                    if field in doc and doc.get(field) is not None
                ]
                unique_count = len(set(str(v) for v in values))

                # If sample shows high unique count, the full dataset likely has more
                if unique_count >= max_values * 0.8 and unique_count >= 10:
                    findings.append(
                        Finding(
                            id="MEILI-S016",
                            category=FindingCategory.SCHEMA,
                            severity=FindingSeverity.SUGGESTION,
                            title="maxValuesPerFacet may be too low",
                            description=(
                                f"The field '{field}' has {unique_count} unique values in the "
                                f"sample documents, approaching the maxValuesPerFacet limit of "
                                f"{max_values}. You may be missing facet values in search results."
                            ),
                            impact="Some facet values may not be returned in search results",
                            index_uid=index.uid,
                            current_value=max_values,
                            recommended_value=min(max_values * 2, 1000),
                            fix=FindingFix(
                                type="settings_update",
                                endpoint=f"PATCH /indexes/{index.uid}/settings",
                                payload={
                                    "faceting": {
                                        "maxValuesPerFacet": min(max_values * 2, 1000)
                                    }
                                },
                            ),
                            references=[
                                "https://www.meilisearch.com/docs/reference/api/settings#faceting"
                            ],
                        )
                    )
                    break  # Only report once

        # Check for very high maxValuesPerFacet
        if max_values > 500:
            findings.append(
                Finding(
                    id="MEILI-S016",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.INFO,
                    title="High maxValuesPerFacet setting",
                    description=(
                        f"maxValuesPerFacet is set to {max_values}. Very high values may "
                        f"impact performance and increase response sizes when using facets."
                    ),
                    impact="Potential performance impact on faceted searches",
                    index_uid=index.uid,
                    current_value=max_values,
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#faceting"
                    ],
                )
            )

        return findings

    def _check_synonyms(self, index: IndexData) -> list[Finding]:
        """Check synonyms configuration (S017)."""
        findings: list[Finding] = []
        settings = index.settings
        synonyms = settings.synonyms

        if not synonyms:
            return findings

        issues: list[str] = []

        # Check for self-synonyms
        self_synonyms = []
        for term, syn_list in synonyms.items():
            if term in syn_list:
                self_synonyms.append(term)

        if self_synonyms:
            issues.append(f"self-synonyms found: {self_synonyms[:5]}")

        # Check for empty synonym lists
        empty_synonyms = [term for term, syn_list in synonyms.items() if not syn_list]
        if empty_synonyms:
            issues.append(f"empty synonym lists: {empty_synonyms[:5]}")

        # Check for very large synonym set
        total_synonyms = sum(len(syn_list) for syn_list in synonyms.values())
        if len(synonyms) > 1000 or total_synonyms > 5000:
            issues.append(
                f"large synonym set ({len(synonyms)} terms, {total_synonyms} total mappings)"
            )

        # Check for very long synonym chains (many synonyms for one term)
        long_chains = [
            (term, len(syn_list))
            for term, syn_list in synonyms.items()
            if len(syn_list) > 20
        ]
        if long_chains:
            issues.append(f"very long synonym chains: {long_chains[:3]}")

        if issues:
            findings.append(
                Finding(
                    id="MEILI-S017",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="Synonyms configuration issues detected",
                    description=(
                        f"Potential issues found in synonyms configuration: {'; '.join(issues)}. "
                        f"Review your synonyms to ensure they are working as intended."
                    ),
                    impact="May affect search relevancy or maintenance complexity",
                    index_uid=index.uid,
                    current_value={
                        "term_count": len(synonyms),
                        "total_mappings": total_synonyms,
                        "issues": issues,
                    },
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#synonyms"
                    ],
                )
            )

        return findings

    def _check_dictionary_settings(self, index: IndexData) -> list[Finding]:
        """Check dictionary and separator token settings (S020)."""
        findings: list[Finding] = []
        settings = index.settings

        issues: list[str] = []

        # Check dictionary size
        if len(settings.dictionary) > 500:
            issues.append(f"large dictionary ({len(settings.dictionary)} entries)")

        # Check for duplicate entries in dictionary
        if len(settings.dictionary) != len(set(settings.dictionary)):
            duplicates = [
                word
                for word in settings.dictionary
                if settings.dictionary.count(word) > 1
            ]
            issues.append(f"duplicate dictionary entries: {list(set(duplicates))[:5]}")

        # Check separator tokens
        suspicious_separators = []
        for token in settings.separator_tokens:
            # Check for alphanumeric separators (usually unintended)
            if token.isalnum():
                suspicious_separators.append(token)
            # Check for very long separators
            elif len(token) > 5:
                suspicious_separators.append(token)

        if suspicious_separators:
            issues.append(f"suspicious separator tokens: {suspicious_separators[:5]}")

        # Check non-separator tokens
        if len(settings.non_separator_tokens) > 100:
            issues.append(
                f"large non-separator token list ({len(settings.non_separator_tokens)} entries)"
            )

        if issues:
            findings.append(
                Finding(
                    id="MEILI-S020",
                    category=FindingCategory.SCHEMA,
                    severity=FindingSeverity.SUGGESTION,
                    title="Dictionary/tokenization configuration issues",
                    description=(
                        f"Potential issues found in dictionary or tokenization settings: "
                        f"{'; '.join(issues)}. Large or misconfigured tokenization settings "
                        f"can impact indexing performance and search behavior."
                    ),
                    impact="May affect indexing performance or search tokenization",
                    index_uid=index.uid,
                    current_value={
                        "dictionary_size": len(settings.dictionary),
                        "separator_tokens": settings.separator_tokens[:10],
                        "non_separator_tokens_count": len(
                            settings.non_separator_tokens
                        ),
                        "issues": issues,
                    },
                    references=[
                        "https://www.meilisearch.com/docs/reference/api/settings#dictionary"
                    ],
                )
            )

        return findings
