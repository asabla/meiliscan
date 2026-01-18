package analyzer

import (
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// CurrentStableVersion is the latest stable Meilisearch version.
// Update this periodically when new versions are released.
const CurrentStableVersion = "1.12.0"

// BestPracticesAnalyzer checks for best practices compliance.
type BestPracticesAnalyzer struct{}

// NewBestPracticesAnalyzer creates a new BestPracticesAnalyzer.
func NewBestPracticesAnalyzer() *BestPracticesAnalyzer {
	return &BestPracticesAnalyzer{}
}

// Name returns the analyzer name.
func (a *BestPracticesAnalyzer) Name() string {
	return "best_practices"
}

// Analyze runs best practices analysis on the collected data.
func (a *BestPracticesAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	// Per-index checks
	for _, idx := range data.Indexes {
		if idx.Settings == nil {
			continue
		}

		// B002: Duplicate searchable/filterable fields
		if f := a.checkDuplicateSearchableFilterable(idx); f != nil {
			findings = append(findings, f)
		}
	}

	// Global checks
	// B001: Settings after documents
	if ff := a.checkSettingsAfterDocuments(data); len(ff) > 0 {
		findings = append(findings, ff...)
	}

	// B003: Missing embedders
	if f := a.checkMissingEmbedders(data); f != nil {
		findings = append(findings, f)
	}

	// B004: Outdated version
	if f := a.checkOutdatedVersion(data); f != nil {
		findings = append(findings, f)
	}

	return findings
}

// B002: Check for fields that are both searchable and filterable.
func (a *BestPracticesAnalyzer) checkDuplicateSearchableFilterable(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	searchable := idx.Settings.SearchableAttributes
	filterable := idx.Settings.FilterableAttributes

	// Skip if wildcard searchable (S001 already covers this)
	if len(searchable) == 1 && searchable[0] == "*" {
		return nil
	}

	// Find duplicates
	searchableSet := make(map[string]bool)
	for _, s := range searchable {
		searchableSet[s] = true
	}

	var duplicates []string
	for _, f := range filterable {
		if searchableSet[f] {
			duplicates = append(duplicates, f)
		}
	}

	if len(duplicates) == 0 {
		return nil
	}

	sort.Strings(duplicates)

	return finding.New(
		"MEILI-B002",
		"Fields in both searchable and filterable attributes",
		fmt.Sprintf("Index '%s' has fields configured as both searchable and filterable: %v. "+
			"This may be intentional if you need to both full-text search AND filter on these fields, "+
			"but often indicates a configuration that could be simplified.", idx.UID, duplicates),
		finding.SeveritySuggestion,
		finding.CategoryBestPractice,
	).WithIndex(idx.UID).
		WithRecommendation("Review if these fields truly need both capabilities. " +
			"Searchable is for full-text search, filterable is for exact matching/filtering.").
		WithDetails(map[string]interface{}{
			"searchable_attributes":  searchable,
			"filterable_attributes":  filterable,
			"duplicate_fields":       duplicates,
			"duplicate_fields_count": len(duplicates),
		})
}

// B001: Check if settings were updated after documents were added.
func (a *BestPracticesAnalyzer) checkSettingsAfterDocuments(data *collector.CollectedData) []*finding.Finding {
	if len(data.Tasks) == 0 {
		return nil
	}

	var findings []*finding.Finding

	// Group tasks by index
	tasksByIndex := make(map[string][]collector.Task)
	for _, task := range data.Tasks {
		if task.IndexUID != "" {
			tasksByIndex[task.IndexUID] = append(tasksByIndex[task.IndexUID], task)
		}
	}

	// Check each index
	for _, idx := range data.Indexes {
		indexTasks := tasksByIndex[idx.UID]
		if len(indexTasks) == 0 {
			continue
		}

		// Sort by enqueued time (need to handle nil pointers)
		sort.Slice(indexTasks, func(i, j int) bool {
			if indexTasks[i].EnqueuedAt == nil {
				return true
			}
			if indexTasks[j].EnqueuedAt == nil {
				return false
			}
			return indexTasks[i].EnqueuedAt.Before(*indexTasks[j].EnqueuedAt)
		})

		// Find first document addition and settings updates after it
		var firstDocTask *collector.Task
		var settingsAfterDocs []collector.Task

		for i := range indexTasks {
			task := &indexTasks[i]

			if task.Type == "documentAdditionOrUpdate" && firstDocTask == nil {
				firstDocTask = task
			}

			// Settings tasks that came after documents
			if firstDocTask != nil && task.Type == "settingsUpdate" {
				settingsAfterDocs = append(settingsAfterDocs, *task)
			}
		}

		if len(settingsAfterDocs) > 0 {
			findings = append(findings, finding.New(
				"MEILI-B001",
				"Settings updated after documents were added",
				fmt.Sprintf("Index '%s' had %d settings update(s) after documents were first added. "+
					"Updating settings after adding documents causes re-indexing, which can be slow for large indexes. "+
					"Best practice is to configure all settings before adding documents.",
					idx.UID, len(settingsAfterDocs)),
				finding.SeverityWarning,
				finding.CategoryBestPractice,
			).WithIndex(idx.UID).
				WithRecommendation("When creating new indexes, configure all settings (searchableAttributes, "+
					"filterableAttributes, sortableAttributes, etc.) before adding documents.").
				WithDetails(map[string]interface{}{
					"settings_updates_after_docs": len(settingsAfterDocs),
				}))
		}
	}

	return findings
}

// B003: Check for indexes that might benefit from embedders/semantic search.
func (a *BestPracticesAnalyzer) checkMissingEmbedders(data *collector.CollectedData) *finding.Finding {
	// Text-heavy field indicators
	textIndicators := []string{
		"content", "body", "text", "description", "article", "post",
		"summary", "excerpt", "abstract", "bio", "review",
	}

	var candidateIndexes []string

	for _, idx := range data.Indexes {
		if idx.NumberOfDocuments < 100 {
			continue
		}

		// Check if index has text-heavy fields (via FieldDistribution)
		if idx.FieldDistribution == nil {
			continue
		}

		for field := range idx.FieldDistribution {
			fieldLower := strings.ToLower(field)
			for _, indicator := range textIndicators {
				if strings.Contains(fieldLower, indicator) {
					candidateIndexes = append(candidateIndexes, idx.UID)
					break
				}
			}
			if len(candidateIndexes) > 0 && candidateIndexes[len(candidateIndexes)-1] == idx.UID {
				break // Already added this index
			}
		}
	}

	if len(candidateIndexes) == 0 {
		return nil
	}

	// Limit to first 5 for readability
	displayIndexes := candidateIndexes
	if len(displayIndexes) > 5 {
		displayIndexes = displayIndexes[:5]
	}

	return finding.New(
		"MEILI-B003",
		"Consider configuring embedders for semantic search",
		fmt.Sprintf("Indexes with text-heavy content detected: %v. "+
			"Meilisearch supports AI-powered semantic/vector search via embedders. "+
			"If you need semantic search capabilities, consider configuring embedders.",
			displayIndexes),
		finding.SeverityInfo,
		finding.CategoryBestPractice,
	).WithRecommendation("See Meilisearch documentation for setting up embedders with OpenAI, HuggingFace, or other providers.").
		WithDetails(map[string]interface{}{
			"text_heavy_indexes": displayIndexes,
			"total_candidates":   len(candidateIndexes),
		})
}

// B004: Check if Meilisearch version is outdated.
func (a *BestPracticesAnalyzer) checkOutdatedVersion(data *collector.CollectedData) *finding.Finding {
	if data.Version == "" {
		return nil
	}

	instanceVersion := strings.TrimPrefix(data.Version, "v")
	stableVersion := CurrentStableVersion

	// Parse versions
	instanceParts := parseVersion(instanceVersion)
	stableParts := parseVersion(stableVersion)

	if len(instanceParts) < 2 || len(stableParts) < 2 {
		return nil
	}

	// Compare major.minor
	majorDiff := stableParts[0] - instanceParts[0]
	minorDiff := stableParts[1] - instanceParts[1]

	// Only flag if at least one minor version behind
	if majorDiff <= 0 && minorDiff < 1 {
		return nil
	}

	severity := finding.SeveritySuggestion
	if majorDiff > 0 {
		severity = finding.SeverityWarning
	}

	return finding.New(
		"MEILI-B004",
		"Outdated Meilisearch version",
		fmt.Sprintf("Running Meilisearch version %s, but the current stable version is %s. "+
			"Newer versions include performance improvements, bug fixes, and new features.",
			data.Version, stableVersion),
		severity,
		finding.CategoryBestPractice,
	).WithRecommendation(fmt.Sprintf("Consider upgrading to Meilisearch %s for the latest features and fixes.", stableVersion)).
		WithDetails(map[string]interface{}{
			"current_version": data.Version,
			"stable_version":  stableVersion,
			"major_behind":    majorDiff,
			"minor_behind":    minorDiff,
		})
}

// parseVersion parses a version string like "1.12.0" into [1, 12, 0].
func parseVersion(v string) []int {
	parts := strings.Split(v, ".")
	result := make([]int, 0, len(parts))
	for _, p := range parts {
		// Strip any non-numeric suffix (e.g., "0-rc1")
		numStr := strings.Split(p, "-")[0]
		num, err := strconv.Atoi(numStr)
		if err != nil {
			break
		}
		result = append(result, num)
	}
	return result
}
