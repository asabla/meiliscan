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

	// S013: Sort candidate patterns
	sortCandidatePatterns = []string{
		".*created.*", ".*updated.*", ".*date.*", ".*time.*",
		".*price.*", ".*rating.*", ".*score.*", ".*rank.*",
		".*order.*", ".*priority.*", ".*popularity.*",
		".*views?$", ".*count$",
	}

	// S015: High cardinality patterns
	highCardinalityPatterns = []string{
		".*email.*", ".*uuid.*", ".*guid.*", ".*token.*", ".*hash.*",
		".*key$", ".*_id$", "^id$", ".*url.*", ".*path.*", ".*slug.*",
	}

	compiledIDPatterns          []*regexp.Regexp
	compiledNumericPatterns     []*regexp.Regexp
	compiledMutablePatterns     []*regexp.Regexp
	compiledSortCandidates      []*regexp.Regexp
	compiledHighCardinalityPats []*regexp.Regexp
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
	for _, p := range sortCandidatePatterns {
		compiledSortCandidates = append(compiledSortCandidates, regexp.MustCompile("(?i)"+p))
	}
	for _, p := range highCardinalityPatterns {
		compiledHighCardinalityPats = append(compiledHighCardinalityPats, regexp.MustCompile("(?i)"+p))
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

		// S010: High pagination limit (separate from S009)
		if f := a.checkHighPaginationLimit(idx); f != nil {
			findings = append(findings, f)
		}

		// S011: Primary key issues
		if ff := a.checkPrimaryKey(idx); len(ff) > 0 {
			findings = append(findings, ff...)
		}

		// S005: Wildcard displayedAttributes with many fields
		if f := a.checkWildcardDisplayed(idx); f != nil {
			findings = append(findings, f)
		}

		// S008: No distinct attribute
		if f := a.checkDistinctAttribute(idx); f != nil {
			findings = append(findings, f)
		}

		// S013: No sortable attributes but has sort candidates
		if f := a.checkNoSortableWithCandidates(idx); f != nil {
			findings = append(findings, f)
		}

		// S014: Sortable attribute type issues
		if ff := a.checkSortableTypes(idx); len(ff) > 0 {
			findings = append(findings, ff...)
		}

		// S015: High-cardinality filterable attributes
		if ff := a.checkFilterableCardinality(idx); len(ff) > 0 {
			findings = append(findings, ff...)
		}

		// S016: Faceting maxValuesPerFacet issues
		if ff := a.checkFacetingSettings(idx); len(ff) > 0 {
			findings = append(findings, ff...)
		}

		// S017: Synonyms configuration issues
		if ff := a.checkSynonyms(idx); len(ff) > 0 {
			findings = append(findings, ff...)
		}

		// S018: Typo tolerance on ID fields
		if f := a.checkTypoToleranceOnIDs(idx); f != nil {
			findings = append(findings, f)
		}

		// S019: Permissive typo tolerance settings
		if f := a.checkPermissiveTypoTolerance(idx); f != nil {
			findings = append(findings, f)
		}

		// S020: Dictionary/tokenization issues
		if ff := a.checkDictionarySettings(idx); len(ff) > 0 {
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

// S010: High pagination limit
func (a *SchemaAnalyzer) checkHighPaginationLimit(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil || idx.Settings.Pagination == nil {
		return nil
	}

	maxHits := idx.Settings.Pagination.MaxTotalHits

	// Very high pagination limit
	if maxHits > 10000 {
		return finding.New(
			"MEILI-S010",
			"High pagination limit",
			fmt.Sprintf("Index '%s' has maxTotalHits set to %d. Very high limits can impact performance on deep pagination.", idx.UID, maxHits),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider if users really need to paginate that far. Lower limits improve performance.").
			WithDetails(map[string]interface{}{
				"current_value": maxHits,
			})
	}

	return nil
}

// S005: Wildcard displayedAttributes with many fields
func (a *SchemaAnalyzer) checkWildcardDisplayed(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	// Check for wildcard displayedAttributes
	displayed := idx.Settings.DisplayedAttributes
	if len(displayed) != 1 || displayed[0] != "*" {
		return nil
	}

	// Count fields from field distribution
	fieldCount := len(idx.FieldDistribution)
	if fieldCount == 0 {
		// Estimate from sample documents
		fields := make(map[string]struct{})
		for _, doc := range idx.SampleDocuments {
			for k := range doc {
				fields[k] = struct{}{}
			}
		}
		fieldCount = len(fields)
	}

	if fieldCount > 20 {
		return finding.New(
			"MEILI-S005",
			"Wildcard displayedAttributes with many fields",
			fmt.Sprintf("Index '%s' has wildcard (*) displayedAttributes but contains %d fields. Consider specifying only needed fields to reduce response size.", idx.UID, fieldCount),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Specify only the fields you need to return in search results to reduce bandwidth and improve performance.").
			WithDetails(map[string]interface{}{
				"field_count": fieldCount,
			})
	}

	return nil
}

// S008: No distinct attribute
func (a *SchemaAnalyzer) checkDistinctAttribute(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	// Only suggest for larger indexes
	if idx.NumberOfDocuments < 1000 {
		return nil
	}

	if idx.Settings.DistinctAttribute == nil || *idx.Settings.DistinctAttribute == "" {
		return finding.New(
			"MEILI-S008",
			"No distinct attribute configured",
			fmt.Sprintf("Index '%s' has no distinct attribute configured. If documents may have near-duplicates, setting a distinct attribute can improve result quality.", idx.UID),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider setting a distinct attribute if your index may return very similar results (e.g., same product in different colors).")
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

// S013: No sortable attributes but has sort candidates
func (a *SchemaAnalyzer) checkNoSortableWithCandidates(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	// Skip if sortable attributes are already configured
	if len(idx.Settings.SortableAttributes) > 0 {
		return nil
	}

	// Collect all fields from field distribution or sample documents
	fields := make(map[string]struct{})
	for field := range idx.FieldDistribution {
		fields[field] = struct{}{}
	}
	for _, doc := range idx.SampleDocuments {
		for k := range doc {
			fields[k] = struct{}{}
		}
	}

	// Find fields that match sort candidate patterns
	var sortCandidates []string
	for field := range fields {
		for _, pattern := range compiledSortCandidates {
			if pattern.MatchString(field) {
				sortCandidates = append(sortCandidates, field)
				break
			}
		}
	}

	if len(sortCandidates) > 0 {
		// Limit to 5 candidates for display
		displayCandidates := sortCandidates
		if len(displayCandidates) > 5 {
			displayCandidates = displayCandidates[:5]
		}

		return finding.New(
			"MEILI-S013",
			"No sortable attributes configured",
			fmt.Sprintf("Index '%s' has no sortable attributes but contains fields commonly used for sorting: %v", idx.UID, displayCandidates),
			finding.SeverityInfo,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider adding these fields to sortableAttributes if you need to sort search results by date, price, popularity, etc.").
			WithDetails(map[string]interface{}{
				"sort_candidates": sortCandidates,
			})
	}

	return nil
}

// S014: Sortable attribute type issues
func (a *SchemaAnalyzer) checkSortableTypes(idx collector.IndexData) []*finding.Finding {
	if idx.Settings == nil || len(idx.Settings.SortableAttributes) == 0 {
		return nil
	}

	if len(idx.SampleDocuments) == 0 {
		return nil
	}

	var findings []*finding.Finding

	for _, attr := range idx.Settings.SortableAttributes {
		// Collect all types for this field across sample documents
		types := make(map[string]bool)
		for _, doc := range idx.SampleDocuments {
			val, exists := doc[attr]
			if !exists || val == nil {
				types["null"] = true
				continue
			}
			switch v := val.(type) {
			case bool:
				types["boolean"] = true
			case float64:
				// JSON numbers are float64, check if it's actually an integer
				if v == float64(int64(v)) {
					types["integer"] = true
				} else {
					types["float"] = true
				}
			case string:
				types["string"] = true
			case []interface{}:
				types["array"] = true
			case map[string]interface{}:
				types["object"] = true
			default:
				types["unknown"] = true
			}
		}

		// Check for complex types (array or object)
		hasComplex := types["array"] || types["object"]
		hasNumeric := types["integer"] || types["float"]
		hasString := types["string"]

		if hasComplex {
			findings = append(findings, finding.New(
				"MEILI-S014",
				"Sortable attribute contains complex types",
				fmt.Sprintf("Index '%s' has sortable attribute '%s' containing array or object values, which cannot be sorted properly.", idx.UID, attr),
				finding.SeverityWarning,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("Sortable attributes should contain scalar values (numbers or strings). Consider flattening or extracting a sortable value.").
				WithDetails(map[string]interface{}{
					"field":       attr,
					"types_found": getMapKeys(types),
				}))
		} else if hasNumeric && hasString {
			findings = append(findings, finding.New(
				"MEILI-S014",
				"Sortable attribute has mixed types",
				fmt.Sprintf("Index '%s' has sortable attribute '%s' containing both numeric and string values, which may cause inconsistent sorting.", idx.UID, attr),
				finding.SeverityWarning,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("Ensure sortable attributes have consistent types across all documents for predictable sorting behavior.").
				WithDetails(map[string]interface{}{
					"field":       attr,
					"types_found": getMapKeys(types),
				}))
		}
	}

	return findings
}

// S015: High-cardinality filterable attributes
func (a *SchemaAnalyzer) checkFilterableCardinality(idx collector.IndexData) []*finding.Finding {
	if idx.Settings == nil || len(idx.Settings.FilterableAttributes) == 0 {
		return nil
	}

	var findings []*finding.Finding

	for _, attr := range idx.Settings.FilterableAttributes {
		// Check by pattern first
		isHighCardinality := false
		for _, pattern := range compiledHighCardinalityPats {
			if pattern.MatchString(attr) {
				isHighCardinality = true
				break
			}
		}

		// If no pattern match, check sample documents for uniqueness
		if !isHighCardinality && len(idx.SampleDocuments) >= 5 {
			values := make(map[string]struct{})
			for _, doc := range idx.SampleDocuments {
				if val, exists := doc[attr]; exists && val != nil {
					values[fmt.Sprintf("%v", val)] = struct{}{}
				}
			}

			// If ≥90% of values are unique, it's high cardinality
			if len(values) >= 5 && float64(len(values)) >= float64(len(idx.SampleDocuments))*0.9 {
				isHighCardinality = true
			}
		}

		if isHighCardinality {
			findings = append(findings, finding.New(
				"MEILI-S015",
				"High-cardinality filterable attribute",
				fmt.Sprintf("Index '%s' has filterable attribute '%s' which appears to have high cardinality (many unique values). This is inefficient for filtering and faceting.", idx.UID, attr),
				finding.SeveritySuggestion,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("High-cardinality fields like IDs, emails, or UUIDs are better suited for direct lookups than filtering. Consider removing from filterableAttributes.").
				WithDetails(map[string]interface{}{
					"field": attr,
				}))
		}
	}

	return findings
}

// S016: Faceting maxValuesPerFacet issues
func (a *SchemaAnalyzer) checkFacetingSettings(idx collector.IndexData) []*finding.Finding {
	if idx.Settings == nil || idx.Settings.Faceting == nil {
		return nil
	}

	var findings []*finding.Finding
	maxValues := idx.Settings.Faceting.MaxValuesPerFacet

	// Check if maxValuesPerFacet is too high
	if maxValues > 500 {
		findings = append(findings, finding.New(
			"MEILI-S016",
			"High maxValuesPerFacet setting",
			fmt.Sprintf("Index '%s' has maxValuesPerFacet set to %d. Very high values can impact performance when faceting.", idx.UID, maxValues),
			finding.SeverityInfo,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider lowering maxValuesPerFacet if you don't need that many facet values. A value of 100-200 is typically sufficient.").
			WithDetails(map[string]interface{}{
				"current_value":     maxValues,
				"recommended_value": 100,
			}))
	}

	// Check if maxValuesPerFacet might be too low for actual data
	if len(idx.Settings.FilterableAttributes) > 0 && len(idx.SampleDocuments) >= 10 {
		for _, attr := range idx.Settings.FilterableAttributes {
			values := make(map[string]struct{})
			for _, doc := range idx.SampleDocuments {
				if val, exists := doc[attr]; exists && val != nil {
					values[fmt.Sprintf("%v", val)] = struct{}{}
				}
			}

			// If unique count in sample is ≥80% of maxValues, might be too low
			uniqueCount := len(values)
			if uniqueCount >= 10 && float64(uniqueCount) >= float64(maxValues)*0.8 {
				suggestedValue := maxValues * 2
				if suggestedValue > 1000 {
					suggestedValue = 1000
				}
				findings = append(findings, finding.New(
					"MEILI-S016",
					"maxValuesPerFacet may be too low",
					fmt.Sprintf("Index '%s' has maxValuesPerFacet=%d, but field '%s' has ~%d unique values in sample. Some facet values may be truncated.", idx.UID, maxValues, attr, uniqueCount),
					finding.SeveritySuggestion,
					finding.CategorySchema,
				).WithIndex(idx.UID).
					WithRecommendation(fmt.Sprintf("Consider increasing maxValuesPerFacet to %d to capture all facet values.", suggestedValue)).
					WithDetails(map[string]interface{}{
						"field":               attr,
						"unique_count_sample": uniqueCount,
						"current_limit":       maxValues,
						"suggested_value":     suggestedValue,
					}))
				break // Only report once
			}
		}
	}

	return findings
}

// S017: Synonyms configuration issues
func (a *SchemaAnalyzer) checkSynonyms(idx collector.IndexData) []*finding.Finding {
	if idx.Settings == nil || len(idx.Settings.Synonyms) == 0 {
		return nil
	}

	var findings []*finding.Finding
	synonyms := idx.Settings.Synonyms

	// Check for self-synonyms and empty lists
	var selfSynonyms []string
	var emptyLists []string
	for term, synList := range synonyms {
		if len(synList) == 0 {
			emptyLists = append(emptyLists, term)
		}
		for _, syn := range synList {
			if strings.EqualFold(term, syn) {
				selfSynonyms = append(selfSynonyms, term)
				break
			}
		}
	}

	if len(selfSynonyms) > 0 {
		displayTerms := selfSynonyms
		if len(displayTerms) > 5 {
			displayTerms = displayTerms[:5]
		}
		findings = append(findings, finding.New(
			"MEILI-S017",
			"Self-referencing synonyms",
			fmt.Sprintf("Index '%s' has terms that include themselves in their synonym list: %v", idx.UID, displayTerms),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Remove self-referencing synonyms as they are redundant.").
			WithDetails(map[string]interface{}{
				"self_synonyms": selfSynonyms,
			}))
	}

	if len(emptyLists) > 0 {
		displayTerms := emptyLists
		if len(displayTerms) > 5 {
			displayTerms = displayTerms[:5]
		}
		findings = append(findings, finding.New(
			"MEILI-S017",
			"Empty synonym lists",
			fmt.Sprintf("Index '%s' has terms with empty synonym lists: %v", idx.UID, displayTerms),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Remove terms with empty synonym lists or add synonyms.").
			WithDetails(map[string]interface{}{
				"empty_lists": emptyLists,
			}))
	}

	// Check for large synonym configuration
	totalTerms := len(synonyms)
	totalMappings := 0
	var longChains []string
	for term, synList := range synonyms {
		totalMappings += len(synList)
		if len(synList) > 20 {
			longChains = append(longChains, term)
		}
	}

	if totalTerms > 1000 || totalMappings > 5000 {
		findings = append(findings, finding.New(
			"MEILI-S017",
			"Large synonym configuration",
			fmt.Sprintf("Index '%s' has a very large synonym configuration (%d terms, %d total mappings). This may impact indexing performance.", idx.UID, totalTerms, totalMappings),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider reducing the synonym configuration to only the most important terms.").
			WithDetails(map[string]interface{}{
				"total_terms":    totalTerms,
				"total_mappings": totalMappings,
			}))
	}

	if len(longChains) > 0 {
		displayTerms := longChains
		if len(displayTerms) > 3 {
			displayTerms = displayTerms[:3]
		}
		findings = append(findings, finding.New(
			"MEILI-S017",
			"Long synonym chains",
			fmt.Sprintf("Index '%s' has terms with very long synonym lists (>20 synonyms): %v", idx.UID, displayTerms),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Long synonym chains may indicate overly broad matching. Consider reducing to only closely related terms.").
			WithDetails(map[string]interface{}{
				"long_chains": longChains,
			}))
	}

	return findings
}

// S018: Typo tolerance on ID fields
func (a *SchemaAnalyzer) checkTypoToleranceOnIDs(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil || idx.Settings.TypoTolerance == nil {
		return nil
	}

	typo := idx.Settings.TypoTolerance

	// Skip if typo tolerance is disabled
	if !typo.Enabled {
		return nil
	}

	// Skip if using wildcard searchable attributes (already caught by S001)
	if len(idx.Settings.SearchableAttributes) == 1 && idx.Settings.SearchableAttributes[0] == "*" {
		return nil
	}

	// Find ID fields in searchable attributes that are NOT protected
	var unprotectedIDFields []string
	for _, attr := range idx.Settings.SearchableAttributes {
		if isIDField(attr) && !containsString(typo.DisableOnAttributes, attr) {
			unprotectedIDFields = append(unprotectedIDFields, attr)
		}
	}

	if len(unprotectedIDFields) > 0 {
		return finding.New(
			"MEILI-S018",
			"Typo tolerance enabled on ID fields",
			fmt.Sprintf("Index '%s' has ID-like fields in searchableAttributes without typo tolerance disabled: %v. Typos in ID searches will return irrelevant results.", idx.UID, unprotectedIDFields),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Add ID fields to typoTolerance.disableOnAttributes to prevent typo corrections on exact identifiers.").
			WithDetails(map[string]interface{}{
				"unprotected_id_fields":    unprotectedIDFields,
				"current_disable_on_attrs": typo.DisableOnAttributes,
			})
	}

	return nil
}

// S019: Permissive typo tolerance settings
func (a *SchemaAnalyzer) checkPermissiveTypoTolerance(idx collector.IndexData) *finding.Finding {
	if idx.Settings == nil || idx.Settings.TypoTolerance == nil {
		return nil
	}

	typo := idx.Settings.TypoTolerance

	// Skip if typo tolerance is disabled
	if !typo.Enabled {
		return nil
	}

	oneTypo := typo.MinWordSizeForTypos.OneTypo
	twoTypos := typo.MinWordSizeForTypos.TwoTypos

	// Check for very permissive settings (defaults are 5 and 9)
	if oneTypo < 3 || twoTypos < 5 {
		return finding.New(
			"MEILI-S019",
			"Very permissive typo tolerance",
			fmt.Sprintf("Index '%s' has very permissive typo tolerance settings (oneTypo=%d, twoTypos=%d). This may return too many irrelevant results.", idx.UID, oneTypo, twoTypos),
			finding.SeverityInfo,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider using default values (oneTypo=5, twoTypos=9) or higher to reduce false positives.").
			WithDetails(map[string]interface{}{
				"current_oneTypo":      oneTypo,
				"current_twoTypos":     twoTypos,
				"recommended_oneTypo":  5,
				"recommended_twoTypos": 9,
			})
	}

	return nil
}

// S020: Dictionary/tokenization issues
func (a *SchemaAnalyzer) checkDictionarySettings(idx collector.IndexData) []*finding.Finding {
	if idx.Settings == nil {
		return nil
	}

	var findings []*finding.Finding

	// Check dictionary size
	if len(idx.Settings.Dictionary) > 500 {
		findings = append(findings, finding.New(
			"MEILI-S020",
			"Large dictionary configuration",
			fmt.Sprintf("Index '%s' has a large dictionary with %d entries. Very large dictionaries can impact indexing performance.", idx.UID, len(idx.Settings.Dictionary)),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider reducing the dictionary to only essential compound words or technical terms.").
			WithDetails(map[string]interface{}{
				"dictionary_size": len(idx.Settings.Dictionary),
			}))
	}

	// Check for duplicate dictionary entries
	if len(idx.Settings.Dictionary) > 0 {
		seen := make(map[string]int)
		var duplicates []string
		for _, word := range idx.Settings.Dictionary {
			lower := strings.ToLower(word)
			seen[lower]++
			if seen[lower] == 2 {
				duplicates = append(duplicates, word)
			}
		}
		if len(duplicates) > 0 {
			displayDupes := duplicates
			if len(displayDupes) > 5 {
				displayDupes = displayDupes[:5]
			}
			findings = append(findings, finding.New(
				"MEILI-S020",
				"Duplicate dictionary entries",
				fmt.Sprintf("Index '%s' has duplicate entries in the dictionary: %v", idx.UID, displayDupes),
				finding.SeveritySuggestion,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("Remove duplicate dictionary entries.").
				WithDetails(map[string]interface{}{
					"duplicates": duplicates,
				}))
		}
	}

	// Check separator tokens for suspicious entries
	if len(idx.Settings.SeparatorTokens) > 0 {
		var suspicious []string
		for _, token := range idx.Settings.SeparatorTokens {
			// Alphanumeric tokens or very long tokens are suspicious
			isAlnum := true
			for _, r := range token {
				if !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
					isAlnum = false
					break
				}
			}
			if (len(token) > 0 && isAlnum) || len(token) > 5 {
				suspicious = append(suspicious, token)
			}
		}
		if len(suspicious) > 0 {
			displaySus := suspicious
			if len(displaySus) > 5 {
				displaySus = displaySus[:5]
			}
			findings = append(findings, finding.New(
				"MEILI-S020",
				"Suspicious separator tokens",
				fmt.Sprintf("Index '%s' has separator tokens that look unusual (alphanumeric or very long): %v", idx.UID, displaySus),
				finding.SeveritySuggestion,
				finding.CategorySchema,
			).WithIndex(idx.UID).
				WithRecommendation("Separator tokens should typically be punctuation or special characters, not words.").
				WithDetails(map[string]interface{}{
					"suspicious_tokens": suspicious,
				}))
		}
	}

	// Check non-separator tokens list size
	if len(idx.Settings.NonSeparatorTokens) > 100 {
		findings = append(findings, finding.New(
			"MEILI-S020",
			"Large non-separator tokens list",
			fmt.Sprintf("Index '%s' has %d non-separator tokens configured. Very large lists can impact tokenization performance.", idx.UID, len(idx.Settings.NonSeparatorTokens)),
			finding.SeveritySuggestion,
			finding.CategorySchema,
		).WithIndex(idx.UID).
			WithRecommendation("Consider reducing the non-separator tokens list to only essential characters.").
			WithDetails(map[string]interface{}{
				"non_separator_count": len(idx.Settings.NonSeparatorTokens),
			}))
	}

	return findings
}

// Helper function to get keys from a map
func getMapKeys(m map[string]bool) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}
