package analyzer

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// Common patterns for field analysis
var (
	idFieldPatterns = []string{
		"^id$", "^_id$", ".*_id$", ".*Id$", ".*ID$", "^uuid$", "^guid$", "^pk$", "^key$",
	}

	numericFieldPatterns = []string{
		".*price.*", ".*amount.*", ".*quantity.*", ".*count.*", ".*total.*",
		".*score.*", ".*rating.*", ".*age.*", ".*year.*", ".*number.*",
	}

	mutableFieldPatterns = []string{
		"^title$", "^name$", "^label$", "^description$", "^content$",
		"^text$", "^body$", "^status$", "^state$", "^email$", "^url$", "^slug$",
	}

	compiledIDPatterns      []*regexp.Regexp
	compiledNumericPatterns []*regexp.Regexp
	compiledMutablePatterns []*regexp.Regexp
)

func init() {
	for _, p := range idFieldPatterns {
		compiledIDPatterns = append(compiledIDPatterns, regexp.MustCompile("(?i)"+p))
	}
	for _, p := range numericFieldPatterns {
		compiledNumericPatterns = append(compiledNumericPatterns, regexp.MustCompile("(?i)"+p))
	}
	for _, p := range mutableFieldPatterns {
		compiledMutablePatterns = append(compiledMutablePatterns, regexp.MustCompile("(?i)"+p))
	}
}

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

		// S003: Numeric fields in searchableAttributes
		if f := a.checkNumericFieldsSearchable(idx); f != nil {
			findings = append(findings, f)
		}

		// S004: Empty filterableAttributes
		if f := a.checkEmptyFilterable(idx); f != nil {
			findings = append(findings, f)
		}

		// S006: No stop words configured
		if f := a.checkStopWords(idx); f != nil {
			findings = append(findings, f)
		}

		// S007: Default ranking rules
		if f := a.checkDefaultRankingRules(idx); f != nil {
			findings = append(findings, f)
		}

		// S009: Pagination limit issues
		if f := a.checkPaginationSettings(idx); f != nil {
			findings = append(findings, f)
		}

		// S011: Primary key issues
		if ff := a.checkPrimaryKey(idx); len(ff) > 0 {
			findings = append(findings, ff...)
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
	var idFields []string

	for _, attr := range idx.Settings.SearchableAttributes {
		if isIDField(attr) {
			idFields = append(idFields, attr)
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

// S003: Numeric fields in searchableAttributes
func (a *SchemaAnalyzer) checkNumericFieldsSearchable(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil || len(idx.Settings.SearchableAttributes) == 0 {
		return nil
	}

	// Skip if wildcard
	if len(idx.Settings.SearchableAttributes) == 1 && idx.Settings.SearchableAttributes[0] == "*" {
		return nil
	}

	var numericFields []string
	for _, attr := range idx.Settings.SearchableAttributes {
		// Skip if already flagged as ID field
		if isIDField(attr) {
			continue
		}
		if isNumericField(attr) {
			numericFields = append(numericFields, attr)
		}
	}

	if len(numericFields) > 0 {
		return finding.New(
			"MEILI-S003",
			"Numeric fields in searchableAttributes",
			fmt.Sprintf("Index '%s' has numeric-looking fields in searchableAttributes: %v. Consider if these should be filterable instead of searchable.", idx.UID, numericFields),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Move numeric fields to filterableAttributes if users need to filter by exact values or ranges.").
			WithDetails(map[string]interface{}{
				"numeric_fields": numericFields,
			})
	}

	return nil
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

// S006: No stop words configured
func (a *SchemaAnalyzer) checkStopWords(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	// Only suggest stop words for indexes with enough documents
	if idx.NumberOfDocuments < 100 {
		return nil
	}

	if len(idx.Settings.StopWords) == 0 {
		return finding.New(
			"MEILI-S006",
			"No stop words configured",
			fmt.Sprintf("Index '%s' has no stop words configured. Adding language-appropriate stop words can improve search relevancy.", idx.UID),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Configure stop words for your language (e.g., 'the', 'a', 'is' for English) to improve search relevancy.")
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

// S009: Pagination settings issues
func (a *SchemaAnalyzer) checkPaginationSettings(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil || idx.Settings.Pagination == nil {
		return nil
	}

	maxHits := idx.Settings.Pagination.MaxTotalHits

	// Very low pagination limit
	if maxHits < 100 {
		return finding.New(
			"MEILI-S009",
			"Very low pagination limit",
			fmt.Sprintf("Index '%s' has maxTotalHits set to %d, which limits accessible results through pagination.", idx.UID, maxHits),
			finding.SeverityWarning,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider increasing maxTotalHits to at least 1000 if users need to access more results.").
			WithDetails(map[string]interface{}{
				"current_value":     maxHits,
				"recommended_value": 1000,
			})
	}

	return nil
}

// S011: Primary key issues
func (a *SchemaAnalyzer) checkPrimaryKey(idx collector.IndexData) []*finding.Finding {
	var findings []*finding.Finding

	// Check if primary key is missing
	if idx.PrimaryKey == "" {
		findings = append(findings, finding.New(
			"MEILI-S011",
			"No primary key defined",
			fmt.Sprintf("Index '%s' has no primary key defined. Meilisearch will auto-detect it from documents, which may cause inconsistent behavior.", idx.UID),
			finding.SeverityCritical,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Explicitly set a primary key when creating the index for consistent document identification."))
		return findings
	}

	// Check if primary key looks like a mutable field
	for _, pattern := range compiledMutablePatterns {
		if pattern.MatchString(idx.PrimaryKey) {
			findings = append(findings, finding.New(
				"MEILI-S012",
				"Primary key appears mutable",
				fmt.Sprintf("Index '%s' uses '%s' as primary key, which appears to be a mutable field. Primary keys should be immutable identifiers.", idx.UID, idx.PrimaryKey),
				finding.SeverityWarning,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("Use a stable, immutable identifier like 'id', 'uuid', or a database primary key.").
				WithDetails(map[string]interface{}{
					"current_primary_key": idx.PrimaryKey,
				}))
			break
		}
	}

	return findings
}

// Helper functions

func isIDField(fieldName string) bool {
	for _, pattern := range compiledIDPatterns {
		if pattern.MatchString(fieldName) {
			return true
		}
	}
	return false
}

func isNumericField(fieldName string) bool {
	for _, pattern := range compiledNumericPatterns {
		if pattern.MatchString(fieldName) {
			return true
		}
	}
	return false
}

func containsString(slice []string, str string) bool {
	for _, s := range slice {
		if strings.EqualFold(s, str) {
			return true
		}
	}
	return false
}
