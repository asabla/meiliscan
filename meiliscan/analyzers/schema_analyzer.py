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

    @property
    def name(self) -> str:
        return "schema"

    def analyze(self, index: IndexData) -> list[Finding]:
        """Analyze index schema and settings."""
        findings: list[Finding] = []

        findings.extend(self._check_searchable_attributes(index))
        findings.extend(self._check_filterable_attributes(index))
        findings.extend(self._check_sortable_attributes(index))
        findings.extend(self._check_displayed_attributes(index))
        findings.extend(self._check_ranking_rules(index))
        findings.extend(self._check_stop_words(index))
        findings.extend(self._check_distinct_attribute(index))
        findings.extend(self._check_pagination_settings(index))
        findings.extend(self._check_typo_tolerance(index))

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
        """Check sortable attributes configuration."""
        # Currently no specific checks, placeholder for future
        return []

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
        """Check typo tolerance settings."""
        # Placeholder for future typo tolerance checks
        return []

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
