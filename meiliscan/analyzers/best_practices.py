"""Best practices analyzer for MeiliSearch instances."""

from packaging import version

from meiliscan.analyzers.base import BaseAnalyzer
from meiliscan.models.finding import (
    Finding,
    FindingCategory,
    FindingSeverity,
)
from meiliscan.models.index import IndexData


# Current stable MeiliSearch version (update periodically)
CURRENT_STABLE_VERSION = "1.12.0"


class BestPracticesAnalyzer(BaseAnalyzer):
    """Analyzer for MeiliSearch best practices compliance."""

    @property
    def name(self) -> str:
        return "best_practices"

    def analyze(self, index: IndexData) -> list[Finding]:
        """Analyze index for best practices compliance.

        Args:
            index: The index data to analyze

        Returns:
            List of findings from the analysis
        """
        findings: list[Finding] = []

        findings.extend(self._check_duplicate_searchable_filterable(index))

        return findings

    def analyze_global(
        self,
        indexes: list[IndexData],
        global_stats: dict,
        tasks: list[dict] | None = None,
        instance_version: str | None = None,
    ) -> list[Finding]:
        """Run global best practices analysis.

        Args:
            indexes: All indexes in the instance
            global_stats: Global stats from the instance
            tasks: Optional task history
            instance_version: MeiliSearch version string

        Returns:
            List of global findings
        """
        findings: list[Finding] = []

        findings.extend(self._check_settings_after_documents(tasks, indexes))
        findings.extend(self._check_missing_embedders(global_stats, indexes))
        findings.extend(self._check_old_version(instance_version))

        return findings

    def _check_duplicate_searchable_filterable(self, index: IndexData) -> list[Finding]:
        """Check for fields that are both searchable and filterable (B002).

        Having the same field in both searchableAttributes and filterableAttributes
        may be intentional, but often indicates a misunderstanding of their purposes.
        """
        findings: list[Finding] = []
        settings = index.settings

        searchable = settings.searchable_attributes
        filterable = settings.filterable_attributes

        # Skip if wildcard searchable (S001 already covers this)
        if searchable == ["*"]:
            return findings

        # Find fields in both lists
        duplicates = set(searchable) & set(filterable)

        if duplicates:
            findings.append(
                Finding(
                    id="MEILI-B002",
                    category=FindingCategory.BEST_PRACTICES,
                    severity=FindingSeverity.SUGGESTION,
                    title="Fields in both searchable and filterable attributes",
                    description=(
                        f"The following fields are configured as both searchable and filterable: "
                        f"{sorted(duplicates)}. This may be intentional if you need to both "
                        f"full-text search AND filter on these fields, but often indicates "
                        f"a configuration that could be simplified."
                    ),
                    impact="Increased index size due to dual indexing",
                    index_uid=index.uid,
                    current_value={
                        "searchable": list(searchable),
                        "filterable": list(filterable),
                        "duplicates": sorted(duplicates),
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/relevancy/displayed_searchable_attributes",
                        "https://www.meilisearch.com/docs/learn/filtering_and_sorting/filter_search_results",
                    ],
                )
            )

        return findings

    def _check_settings_after_documents(
        self, tasks: list[dict] | None, indexes: list[IndexData]
    ) -> list[Finding]:
        """Check if settings were configured after documents were added (B001).

        Best practice is to configure settings BEFORE adding documents to avoid
        unnecessary re-indexing.
        """
        findings: list[Finding] = []

        if not tasks:
            return findings

        # Group tasks by index
        tasks_by_index: dict[str, list[dict]] = {}
        for task in tasks:
            index_uid = task.get("indexUid")
            if index_uid:
                if index_uid not in tasks_by_index:
                    tasks_by_index[index_uid] = []
                tasks_by_index[index_uid].append(task)

        # Check each index
        for index in indexes:
            index_tasks = tasks_by_index.get(index.uid, [])
            if not index_tasks:
                continue

            # Sort by enqueuedAt to get chronological order
            sorted_tasks = sorted(
                index_tasks,
                key=lambda t: t.get("enqueuedAt", ""),
            )

            # Find first document addition and first settings update
            first_doc_task = None
            settings_after_docs = []

            for task in sorted_tasks:
                task_type = task.get("type", "")

                if task_type == "documentAdditionOrUpdate" and first_doc_task is None:
                    first_doc_task = task

                # Settings tasks that came after documents
                if first_doc_task and task_type == "settingsUpdate":
                    settings_after_docs.append(task)

            if settings_after_docs:
                # Get details about what settings were changed
                setting_types = set()
                for task in settings_after_docs:
                    details = task.get("details", {})
                    if isinstance(details, dict):
                        setting_types.update(details.keys())

                findings.append(
                    Finding(
                        id="MEILI-B001",
                        category=FindingCategory.BEST_PRACTICES,
                        severity=FindingSeverity.WARNING,
                        title="Settings updated after documents were added",
                        description=(
                            f"Index '{index.uid}' had {len(settings_after_docs)} settings update(s) "
                            f"after documents were first added. Updating settings after adding "
                            f"documents causes re-indexing, which can be slow for large indexes. "
                            f"Best practice is to configure all settings before adding documents."
                        ),
                        impact="Causes re-indexing of all documents, slower initial setup",
                        index_uid=index.uid,
                        current_value={
                            "settings_updates_after_docs": len(settings_after_docs),
                            "settings_changed": sorted(setting_types)
                            if setting_types
                            else None,
                        },
                        references=[
                            "https://www.meilisearch.com/docs/learn/getting_started/customizing_relevancy"
                        ],
                    )
                )

        return findings

    def _check_missing_embedders(
        self, global_stats: dict, indexes: list[IndexData]
    ) -> list[Finding]:
        """Check for missing embedders configuration (B003).

        If the instance appears to be a candidate for semantic/vector search
        but has no embedders configured, suggest setting them up.
        """
        findings: list[Finding] = []

        # Check if any index has embedders configured
        # Note: embedders info would typically be in settings, but we check for
        # text-heavy indexes that might benefit from semantic search

        has_large_text_content = False
        candidate_indexes = []

        for index in indexes:
            # Check if index has significant text content
            # Look for fields that suggest text-heavy content
            text_indicators = [
                "content",
                "body",
                "text",
                "description",
                "article",
                "post",
            ]

            for field in index.stats.field_distribution.keys():
                if any(indicator in field.lower() for indicator in text_indicators):
                    if index.document_count > 100:  # Non-trivial size
                        has_large_text_content = True
                        candidate_indexes.append(index.uid)
                        break

        # Only suggest if there are text-heavy indexes and no embedders
        # Note: We can't directly detect embedders from current data model,
        # so this is informational for indexes that might benefit
        if has_large_text_content and len(candidate_indexes) > 0:
            findings.append(
                Finding(
                    id="MEILI-B003",
                    category=FindingCategory.BEST_PRACTICES,
                    severity=FindingSeverity.INFO,
                    title="Consider configuring embedders for semantic search",
                    description=(
                        f"Indexes with text-heavy content detected: {candidate_indexes[:5]}. "
                        f"MeiliSearch supports AI-powered semantic/vector search via embedders. "
                        f"If you need semantic search capabilities, consider configuring embedders."
                    ),
                    impact="Semantic search not available without embedder configuration",
                    current_value={
                        "text_heavy_indexes": candidate_indexes[:5],
                        "total_candidates": len(candidate_indexes),
                    },
                    references=[
                        "https://www.meilisearch.com/docs/learn/ai_powered_search/getting_started_with_ai_search"
                    ],
                )
            )

        return findings

    def _check_old_version(self, instance_version: str | None) -> list[Finding]:
        """Check if MeiliSearch version is outdated (B004)."""
        findings: list[Finding] = []

        if not instance_version:
            return findings

        # Clean version string (remove 'v' prefix if present)
        clean_version = instance_version.lstrip("v")

        # Parse versions for comparison
        try:
            current = version.parse(clean_version)
            stable = version.parse(CURRENT_STABLE_VERSION)

            # Only flag if significantly behind (major or minor version)
            if current < stable:
                # Calculate how far behind
                current_parts = clean_version.split(".")
                stable_parts = CURRENT_STABLE_VERSION.split(".")

                major_diff = (
                    int(stable_parts[0]) - int(current_parts[0])
                    if len(current_parts) > 0 and len(stable_parts) > 0
                    else 0
                )
                minor_diff = (
                    int(stable_parts[1]) - int(current_parts[1])
                    if len(current_parts) > 1 and len(stable_parts) > 1
                    else 0
                )

                # Only suggest if at least one minor version behind
                if major_diff > 0 or minor_diff >= 1:
                    severity = (
                        FindingSeverity.WARNING
                        if major_diff > 0
                        else FindingSeverity.SUGGESTION
                    )

                    findings.append(
                        Finding(
                            id="MEILI-B004",
                            category=FindingCategory.BEST_PRACTICES,
                            severity=severity,
                            title="Outdated MeiliSearch version",
                            description=(
                                f"Running MeiliSearch version {instance_version}, but the current "
                                f"stable version is {CURRENT_STABLE_VERSION}. Newer versions include "
                                f"performance improvements, bug fixes, and new features."
                            ),
                            impact="Missing latest features, performance improvements, and security fixes",
                            current_value=instance_version,
                            recommended_value=CURRENT_STABLE_VERSION,
                            references=[
                                "https://github.com/meilisearch/meilisearch/releases",
                                "https://www.meilisearch.com/docs/learn/update_and_migration/updating",
                            ],
                        )
                    )

        except (ValueError, TypeError, IndexError):
            # If we can't parse the version, skip this check
            pass

        return findings
