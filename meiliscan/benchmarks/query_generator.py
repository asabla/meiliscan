"""Query generator for benchmark testing."""

import random
from typing import Any

from meiliscan.models.benchmark import SearchQuery
from meiliscan.models.index import IndexData


class QueryGenerator:
    """Generates test queries for benchmarking based on index configuration."""

    # Common words to use in text queries
    COMMON_WORDS = [
        "the",
        "be",
        "to",
        "of",
        "and",
        "a",
        "in",
        "that",
        "have",
        "it",
        "for",
        "not",
        "on",
        "with",
        "he",
        "as",
        "you",
        "do",
        "at",
        "this",
        "but",
        "his",
        "by",
        "from",
        "they",
        "we",
        "say",
        "her",
        "she",
        "or",
        "an",
        "will",
        "my",
        "one",
        "all",
        "would",
        "there",
        "their",
        "what",
    ]

    def __init__(self, seed: int | None = None):
        """Initialize the query generator.

        Args:
            seed: Optional random seed for reproducibility
        """
        self._random = random.Random(seed)

    def generate_baseline_query(self, index: IndexData) -> SearchQuery:
        """Generate a baseline (empty) query.

        Args:
            index: The index to generate a query for

        Returns:
            SearchQuery with empty query string
        """
        return SearchQuery(
            query_type="baseline",
            query_text="",
            filter=None,
            sort=None,
            facets=None,
        )

    def generate_text_query(self, index: IndexData, num_words: int = 2) -> SearchQuery:
        """Generate a text search query.

        Args:
            index: The index to generate a query for
            num_words: Number of words in the query

        Returns:
            SearchQuery with random words
        """
        words = self._random.sample(
            self.COMMON_WORDS, min(num_words, len(self.COMMON_WORDS))
        )
        query_text = " ".join(words)

        return SearchQuery(
            query_type="text",
            query_text=query_text,
            filter=None,
            sort=None,
            facets=None,
        )

    def generate_filtered_query(
        self, index: IndexData, sample_documents: list[dict[str, Any]] | None = None
    ) -> SearchQuery | None:
        """Generate a query with a filter.

        Args:
            index: The index to generate a query for
            sample_documents: Optional sample documents to extract filter values from

        Returns:
            SearchQuery with filter, or None if no filterable attributes
        """
        filterable = index.settings.filterable_attributes
        if not filterable:
            return None

        # Pick a random filterable attribute
        attr = self._random.choice(filterable)

        # Try to get a real value from sample documents
        filter_value = None
        if sample_documents:
            for doc in sample_documents:
                if attr in doc and doc[attr] is not None:
                    filter_value = doc[attr]
                    break

        # Build filter expression
        if filter_value is not None:
            if isinstance(filter_value, str):
                filter_expr = f'{attr} = "{filter_value}"'
            elif isinstance(filter_value, bool):
                filter_expr = f"{attr} = {str(filter_value).lower()}"
            elif isinstance(filter_value, (int, float)):
                filter_expr = f"{attr} = {filter_value}"
            else:
                # Default to EXISTS for complex types
                filter_expr = f"{attr} EXISTS"
        else:
            # Use EXISTS if no sample value available
            filter_expr = f"{attr} EXISTS"

        return SearchQuery(
            query_type="filtered",
            query_text="",
            filter=filter_expr,
            sort=None,
            facets=None,
        )

    def generate_sorted_query(self, index: IndexData) -> SearchQuery | None:
        """Generate a query with sorting.

        Args:
            index: The index to generate a query for

        Returns:
            SearchQuery with sort, or None if no sortable attributes
        """
        sortable = index.settings.sortable_attributes
        if not sortable:
            return None

        # Pick a random sortable attribute and direction
        attr = self._random.choice(sortable)
        direction = self._random.choice(["asc", "desc"])

        return SearchQuery(
            query_type="sorted",
            query_text="",
            filter=None,
            sort=[f"{attr}:{direction}"],
            facets=None,
        )

    def generate_faceted_query(self, index: IndexData) -> SearchQuery | None:
        """Generate a query with facets.

        Args:
            index: The index to generate a query for

        Returns:
            SearchQuery with facets, or None if no filterable attributes
        """
        filterable = index.settings.filterable_attributes
        if not filterable:
            return None

        # Select up to 3 random attributes for faceting
        num_facets = min(3, len(filterable))
        facet_attrs = self._random.sample(filterable, num_facets)

        return SearchQuery(
            query_type="faceted",
            query_text="",
            filter=None,
            sort=None,
            facets=facet_attrs,
        )

    def generate_complex_query(
        self, index: IndexData, sample_documents: list[dict[str, Any]] | None = None
    ) -> SearchQuery:
        """Generate a complex query combining multiple features.

        Args:
            index: The index to generate a query for
            sample_documents: Optional sample documents for filter values

        Returns:
            SearchQuery with multiple features combined
        """
        # Start with text search
        words = self._random.sample(self.COMMON_WORDS, 2)
        query_text = " ".join(words)

        # Add filter if possible
        filter_expr = None
        filterable = index.settings.filterable_attributes
        if filterable:
            attr = self._random.choice(filterable)
            filter_expr = f"{attr} EXISTS"

        # Add sort if possible
        sort = None
        sortable = index.settings.sortable_attributes
        if sortable:
            attr = self._random.choice(sortable)
            sort = [f"{attr}:asc"]

        # Add facets if possible
        facets = None
        if filterable and len(filterable) >= 2:
            facets = self._random.sample(filterable, min(2, len(filterable)))

        return SearchQuery(
            query_type="complex",
            query_text=query_text,
            filter=filter_expr,
            sort=sort,
            facets=facets,
        )

    def generate_all_queries(
        self, index: IndexData, sample_documents: list[dict[str, Any]] | None = None
    ) -> list[SearchQuery]:
        """Generate all types of queries for an index.

        Args:
            index: The index to generate queries for
            sample_documents: Optional sample documents for filter values

        Returns:
            List of all generated queries (some may be None and are filtered out)
        """
        queries = [
            self.generate_baseline_query(index),
            self.generate_text_query(index),
            self.generate_filtered_query(index, sample_documents),
            self.generate_sorted_query(index),
            self.generate_faceted_query(index),
            self.generate_complex_query(index, sample_documents),
        ]

        return [q for q in queries if q is not None]
