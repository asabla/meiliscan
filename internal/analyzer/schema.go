package analyzer

import (
	"fmt"
	"strings"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// SchemaAnalyzer analyzes index schema configuration.
type SchemaAnalyzer struct{}

// NewSchemaAnalyzer creates a new SchemaAnalyzer.
func NewSchemaAnalyzer() *SchemaAnalyzer {
	return &SchemaAnalyzer{}
}

// Name returns the analyzer name.
func (a *SchemaAnalyzer) Name() string {
	return "schema"
}

// Analyze runs schema analysis on the collected data.
func (a *SchemaAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	for _, idx := range data.Indexes {
		if idx.Settings == nil {
			continue
		}

		// S001: Wildcard searchableAttributes
		if f := a.checkWildcardSearchable(idx); f != nil {
			findings = append(findings, f)
		}

		// S002: ID fields in searchableAttributes
		if ff := a.checkIDFieldsSearchable(idx); len(ff) > 0 {
			findings = append(findings, ff...)
		}

		// S004: Empty filterableAttributes
		if f := a.checkEmptyFilterable(idx); f != nil {
			findings = append(findings, f)
		}

		// S007: Default ranking rules
		if f := a.checkDefaultRankingRules(idx); f != nil {
			findings = append(findings, f)
		}
	}

	return findings
}

// S001: Wildcard searchableAttributes
func (a *SchemaAnalyzer) checkWildcardSearchable(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil || len(idx.Settings.SearchableAttributes) == 0 {
		return nil
	}

	// Check if first attribute is "*" (wildcard)
	if len(idx.Settings.SearchableAttributes) == 1 && idx.Settings.SearchableAttributes[0] == "*" {
		f := finding.New(
			"MEILI-S001",
			"Wildcard searchableAttributes",
			fmt.Sprintf("Index '%s' has wildcard (*) searchableAttributes, which makes all fields searchable including IDs, numbers, and other non-text fields. This impacts search relevancy and performance.", idx.UID),
			finding.SeverityCritical,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Explicitly list the text fields that should be searchable, ordered by importance.").
			WithDetails(map[string]interface{}{
				"current_setting": idx.Settings.SearchableAttributes,
			})

		return f
	}

	return nil
}

// S002: ID fields in searchableAttributes
func (a *SchemaAnalyzer) checkIDFieldsSearchable(idx collector.IndexData) []*finding.Finding {
	if idx.Settings == nil || len(idx.Settings.SearchableAttributes) == 0 {
		return nil
	}

	// Skip if wildcard (already caught by S001)
	if len(idx.Settings.SearchableAttributes) == 1 && idx.Settings.SearchableAttributes[0] == "*" {
		return nil
	}

	var findings []*finding.Finding
	idPatterns := []string{"id", "_id", "uid", "uuid", "guid", "key", "pk"}

	var idFields []string
	for _, attr := range idx.Settings.SearchableAttributes {
		attrLower := strings.ToLower(attr)
		for _, pattern := range idPatterns {
			if strings.Contains(attrLower, pattern) || strings.HasSuffix(attrLower, pattern) {
				idFields = append(idFields, attr)
				break
			}
		}
	}

	if len(idFields) > 0 {
		f := finding.New(
			"MEILI-S002",
			"ID fields in searchableAttributes",
			fmt.Sprintf("Index '%s' has ID-like fields in searchableAttributes: %v. Users typically don't search by IDs.", idx.UID, idFields),
			finding.SeverityWarning,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Remove ID fields from searchableAttributes. If you need to look up by ID, use the document API directly or make these fields filterable.").
			WithDetails(map[string]interface{}{
				"id_fields": idFields,
			})

		findings = append(findings, f)
	}

	return findings
}

// S004: Empty filterableAttributes
func (a *SchemaAnalyzer) checkEmptyFilterable(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	if len(idx.Settings.FilterableAttributes) == 0 {
		f := finding.New(
			"MEILI-S004",
			"Empty filterableAttributes",
			fmt.Sprintf("Index '%s' has no filterable attributes configured. Users won't be able to filter or facet search results.", idx.UID),
			finding.SeverityInfo,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Add commonly filtered fields (categories, tags, dates, status) to filterableAttributes.")

		return f
	}

	return nil
}

// S007: Default ranking rules
func (a *SchemaAnalyzer) checkDefaultRankingRules(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	defaultRules := []string{"words", "typo", "proximity", "attribute", "sort", "exactness"}

	if len(idx.Settings.RankingRules) == len(defaultRules) {
		isDefault := true
		for i, rule := range idx.Settings.RankingRules {
			if rule != defaultRules[i] {
				isDefault = false
				break
			}
		}

		if isDefault {
			f := finding.New(
				"MEILI-S007",
				"Default ranking rules",
				fmt.Sprintf("Index '%s' is using default ranking rules. Custom ranking rules can improve search relevancy for your specific use case.", idx.UID),
				finding.SeverityInfo,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("Consider customizing ranking rules based on your use case. For example, add custom ranking by popularity, date, or other business-relevant fields.").
				WithDetails(map[string]interface{}{
					"current_rules": idx.Settings.RankingRules,
				})

			return f
		}
	}

	return nil
}
