package analyzer

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// Markup patterns for detecting HTML/Markdown
var markupPatterns = []*regexp.Regexp{
	regexp.MustCompile(`<[^>]+>`),             // HTML tags
	regexp.MustCompile(`\[.*?\]\(.*?\)`),      // Markdown links
	regexp.MustCompile(`#{1,6}\s`),            // Markdown headers
	regexp.MustCompile(`\*{1,2}[^*]+\*{1,2}`), // Bold/italic
}

// Geo coordinate field patterns
var geoFieldPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)^(lat|latitude)$`),
	regexp.MustCompile(`(?i)^(lng|lon|long|longitude)$`),
	regexp.MustCompile(`(?i)(location|coordinates?|position|geo)`),
}

// Date patterns in strings
var datePatterns = []*regexp.Regexp{
	regexp.MustCompile(`^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?`), // ISO 8601
	regexp.MustCompile(`^\d{2}/\d{2}/\d{4}$`),                     // US format
	regexp.MustCompile(`^\d{2}-\d{2}-\d{4}$`),                     // European format
	regexp.MustCompile(`^\d{10}(\d{3})?$`),                        // Unix timestamp
}

// Field names suggesting dates/times
var dateFieldPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)(created|updated|modified|deleted)_?(at|on|date|time)?$`),
	regexp.MustCompile(`(?i)^(date|time|timestamp|datetime)`),
	regexp.MustCompile(`(?i)(start|end|begin|finish)_?(date|time)?$`),
	regexp.MustCompile(`(?i)(published|posted|submitted)_?(at|on|date)?$`),
	regexp.MustCompile(`(?i)_?(date|time|at)$`),
}

// PII detection patterns
var piiPatterns = map[string]*regexp.Regexp{
	"email":       regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`),
	"phone":       regexp.MustCompile(`(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}`),
	"ssn":         regexp.MustCompile(`\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b`),
	"credit_card": regexp.MustCompile(`\b(?:\d{4}[-\s]?){3}\d{4}\b`),
	"ip_address":  regexp.MustCompile(`\b(?:\d{1,3}\.){3}\d{1,3}\b`),
}

// Sensitive field name patterns
var sensitiveFieldPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)^(email|e_mail|e-mail|mail)$`),
	regexp.MustCompile(`(?i)(password|passwd|pwd|secret|token|api_key|apikey)`),
	regexp.MustCompile(`(?i)(ssn|social_security|social-security)`),
	regexp.MustCompile(`(?i)(credit.?card|card.?number|ccn)`),
	regexp.MustCompile(`(?i)(phone|mobile|cell|tel|fax)`),
	regexp.MustCompile(`(?i)(address|street|zip|postal)`),
	regexp.MustCompile(`(?i)(birth.?date|dob|birthday|date.?of.?birth)`),
	regexp.MustCompile(`(?i)(driver.?license|passport|national.?id)`),
	regexp.MustCompile(`(?i)(salary|income|wage|compensation)`),
	regexp.MustCompile(`(?i)(bank|account|routing|iban|swift)`),
}

// DocumentAnalyzer analyzes document structure and content.
type DocumentAnalyzer struct{}

// NewDocumentAnalyzer creates a new DocumentAnalyzer.
func NewDocumentAnalyzer() *DocumentAnalyzer {
	return &DocumentAnalyzer{}
}

// Name returns the analyzer name.
func (a *DocumentAnalyzer) Name() string {
	return "documents"
}

// Analyze runs document analysis on the collected data.
func (a *DocumentAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	for _, idx := range data.Indexes {
		// Skip indexes without sample documents
		if len(idx.SampleDocuments) == 0 {
			continue
		}

		// D009: Sensitive field names
		if f := a.checkSensitiveFieldNames(idx); f != nil {
			findings = append(findings, f)
		}

		// D010: PII in content
		if f := a.checkPIIContent(idx); f != nil {
			findings = append(findings, f)
		}

		// D001: Large documents
		if f := a.checkDocumentSize(idx); f != nil {
			findings = append(findings, f)
		}

		// D003: Deep nesting
		if f := a.checkNestingDepth(idx); f != nil {
			findings = append(findings, f)
		}

		// D002: Inconsistent schema
		if f := a.checkSchemaConsistency(idx); f != nil {
			findings = append(findings, f)
		}

		// D004: Large arrays
		if f := a.checkArraySizes(idx); f != nil {
			findings = append(findings, f)
		}

		// D005: Markup in text fields
		if f := a.checkMarkupContent(idx); f != nil {
			findings = append(findings, f)
		}

		// D006: Empty field values
		if f := a.checkEmptyFields(idx); f != nil {
			findings = append(findings, f)
		}

		// D007: Mixed types in fields
		if f := a.checkMixedTypes(idx); f != nil {
			findings = append(findings, f)
		}

		// D008: Very long text fields
		if f := a.checkTextLength(idx); f != nil {
			findings = append(findings, f)
		}

		// D011: Arrays of objects
		if f := a.checkArraysOfObjects(idx); f != nil {
			findings = append(findings, f)
		}

		// D012: Geo coordinates without _geo
		if f := a.checkGeoCoordinates(idx); f != nil {
			findings = append(findings, f)
		}

		// D013: Date strings that should be numeric
		if f := a.checkDateStrings(idx); f != nil {
			findings = append(findings, f)
		}
	}

	return findings
}

// D009: Check for sensitive field names
func (a *DocumentAnalyzer) checkSensitiveFieldNames(idx collector.IndexData) *finding.Finding {
	allFields := make(map[string]struct{})

	// Collect all field names from sample documents
	for _, doc := range idx.SampleDocuments {
		collectFieldNames(doc, "", allFields)
	}

	var sensitiveFields []string
	for field := range allFields {
		// Get the leaf field name
		parts := strings.Split(field, ".")
		leafField := parts[len(parts)-1]

		for _, pattern := range sensitiveFieldPatterns {
			if pattern.MatchString(leafField) {
				sensitiveFields = append(sensitiveFields, field)
				break
			}
		}
	}

	if len(sensitiveFields) > 0 {
		return finding.New(
			"MEILI-D009",
			"Potentially sensitive field names",
			fmt.Sprintf("Index '%s' has fields with names suggesting sensitive data: %v. Review whether these should be indexed.", idx.UID, truncateSlice(sensitiveFields, 5)),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider excluding sensitive fields from searchableAttributes or not indexing them at all.").
			WithDetails(map[string]interface{}{
				"sensitive_fields": sensitiveFields,
			})
	}

	return nil
}

// D010: Check for PII patterns in content
func (a *DocumentAnalyzer) checkPIIContent(idx collector.IndexData) *finding.Finding {
	piiDetections := make(map[string][]string) // field -> [pii types]

	for _, doc := range idx.SampleDocuments {
		scanForPII(doc, "", piiDetections)
	}

	if len(piiDetections) > 0 {
		// Get unique PII types found
		piiTypes := make(map[string]struct{})
		for _, types := range piiDetections {
			for _, t := range types {
				piiTypes[t] = struct{}{}
			}
		}

		typesList := make([]string, 0, len(piiTypes))
		for t := range piiTypes {
			typesList = append(typesList, t)
		}

		fields := make([]string, 0, len(piiDetections))
		for field := range piiDetections {
			fields = append(fields, field)
		}

		return finding.New(
			"MEILI-D010",
			"Potential PII detected in content",
			fmt.Sprintf("Index '%s' has fields containing data matching PII patterns: %v. Detected types: %v.", idx.UID, truncateSlice(fields, 5), typesList),
			finding.SeverityCritical,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Review and mask or exclude PII data from search indexes. Consider using tenant tokens for access control.").
			WithDetails(map[string]interface{}{
				"fields_with_pii": piiDetections,
				"pii_types_found": typesList,
			})
	}

	return nil
}

// D001: Check document size
func (a *DocumentAnalyzer) checkDocumentSize(idx collector.IndexData) *finding.Finding {
	var totalSize int64
	var maxSize int64

	for _, doc := range idx.SampleDocuments {
		size := estimateDocSize(doc)
		totalSize += size
		if size > maxSize {
			maxSize = size
		}
	}

	if len(idx.SampleDocuments) == 0 {
		return nil
	}

	avgSize := totalSize / int64(len(idx.SampleDocuments))

	// Flag if average > 10KB or max > 100KB
	if avgSize > 10*1024 || maxSize > 100*1024 {
		return finding.New(
			"MEILI-D001",
			"Large documents detected",
			fmt.Sprintf("Index '%s' has large documents (avg: %.1fKB, max: %.1fKB). Large documents slow down indexing and search.", idx.UID, float64(avgSize)/1024, float64(maxSize)/1024),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider reducing document size by removing unnecessary fields or storing large content elsewhere.").
			WithDetails(map[string]interface{}{
				"avg_size_kb": float64(avgSize) / 1024,
				"max_size_kb": float64(maxSize) / 1024,
			})
	}

	return nil
}

// D003: Check nesting depth
func (a *DocumentAnalyzer) checkNestingDepth(idx collector.IndexData) *finding.Finding {
	maxDepth := 0

	for _, doc := range idx.SampleDocuments {
		depth := getMaxDepth(doc, 0)
		if depth > maxDepth {
			maxDepth = depth
		}
	}

	if maxDepth > 3 {
		return finding.New(
			"MEILI-D003",
			"Deep document nesting",
			fmt.Sprintf("Index '%s' has documents with nesting depth of %d. Meilisearch flattens nested objects, which can lead to unexpected field names.", idx.UID, maxDepth),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider flattening document structure to avoid deeply nested fields.").
			WithDetails(map[string]interface{}{
				"max_depth":         maxDepth,
				"recommended_depth": 3,
			})
	}

	return nil
}

// D002: Check schema consistency
func (a *DocumentAnalyzer) checkSchemaConsistency(idx collector.IndexData) *finding.Finding {
	if len(idx.SampleDocuments) < 10 {
		return nil // Need enough samples
	}

	fieldCounts := make(map[string]int)
	totalDocs := len(idx.SampleDocuments)

	for _, doc := range idx.SampleDocuments {
		for field := range doc {
			fieldCounts[field]++
		}
	}

	// Find inconsistent fields (present in 20-80% of documents)
	var inconsistentFields []string
	for field, count := range fieldCounts {
		ratio := float64(count) / float64(totalDocs)
		if ratio > 0.2 && ratio < 0.8 {
			inconsistentFields = append(inconsistentFields, field)
		}
	}

	if len(inconsistentFields) > 0 {
		return finding.New(
			"MEILI-D002",
			"Inconsistent document schema",
			fmt.Sprintf("Index '%s' has fields that appear in only some documents: %v. This may indicate schema issues.", idx.UID, truncateSlice(inconsistentFields, 5)),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Review the schema - inconsistent fields may cause search and filter issues.").
			WithDetails(map[string]interface{}{
				"inconsistent_fields": inconsistentFields,
				"sample_size":         totalDocs,
			})
	}

	return nil
}

// D004: Check array sizes
func (a *DocumentAnalyzer) checkArraySizes(idx collector.IndexData) *finding.Finding {
	arrayStats := make(map[string][]int) // field -> sizes

	for _, doc := range idx.SampleDocuments {
		collectArrayStats(doc, "", arrayStats)
	}

	// Find large arrays (avg > 50 elements)
	var largeArrays []string
	largeArrayDetails := make(map[string]float64)

	for field, sizes := range arrayStats {
		if len(sizes) == 0 {
			continue
		}
		var sum int
		for _, s := range sizes {
			sum += s
		}
		avg := float64(sum) / float64(len(sizes))
		if avg > 50 {
			largeArrays = append(largeArrays, field)
			largeArrayDetails[field] = avg
		}
	}

	if len(largeArrays) > 0 {
		return finding.New(
			"MEILI-D004",
			"Large array fields detected",
			fmt.Sprintf("Index '%s' has array fields with high element counts: %v. Large arrays can slow down filtering.", idx.UID, truncateSlice(largeArrays, 3)),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider restructuring data or limiting array sizes for better performance.").
			WithDetails(map[string]interface{}{
				"large_arrays_avg_size": largeArrayDetails,
			})
	}

	return nil
}

// D005: Check for markup content
func (a *DocumentAnalyzer) checkMarkupContent(idx collector.IndexData) *finding.Finding {
	markupFields := make(map[string]struct{})

	for _, doc := range idx.SampleDocuments {
		findMarkupFields(doc, "", markupFields)
	}

	if len(markupFields) > 0 {
		fields := make([]string, 0, len(markupFields))
		for f := range markupFields {
			fields = append(fields, f)
		}

		return finding.New(
			"MEILI-D005",
			"HTML/Markdown content in text fields",
			fmt.Sprintf("Index '%s' has fields containing HTML or Markdown: %v. Consider stripping markup for better search results.", idx.UID, truncateSlice(fields, 5)),
			finding.SeveritySuggestion,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Strip HTML/Markdown before indexing to avoid markup appearing in search results.").
			WithDetails(map[string]interface{}{
				"fields_with_markup": fields,
			})
	}

	return nil
}

// D006: Check for empty fields
func (a *DocumentAnalyzer) checkEmptyFields(idx collector.IndexData) *finding.Finding {
	fieldEmptyCounts := make(map[string]int)
	fieldTotalCounts := make(map[string]int)

	for _, doc := range idx.SampleDocuments {
		countEmptyFields(doc, "", fieldEmptyCounts, fieldTotalCounts)
	}

	// Find fields with >30% empty ratio
	var highEmptyFields []string
	emptyRatios := make(map[string]string)

	for field, emptyCount := range fieldEmptyCounts {
		total := fieldTotalCounts[field]
		if total > 0 {
			ratio := float64(emptyCount) / float64(total)
			if ratio > 0.3 {
				highEmptyFields = append(highEmptyFields, field)
				emptyRatios[field] = fmt.Sprintf("%.0f%%", ratio*100)
			}
		}
	}

	if len(highEmptyFields) > 0 {
		return finding.New(
			"MEILI-D006",
			"High empty/null field ratio",
			fmt.Sprintf("Index '%s' has fields with >30%% null/empty values: %v.", idx.UID, truncateSlice(highEmptyFields, 3)),
			finding.SeverityInfo,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider if these fields should be optional or if data quality could be improved.").
			WithDetails(map[string]interface{}{
				"empty_ratios": emptyRatios,
			})
	}

	return nil
}

// D007: Check for mixed types
func (a *DocumentAnalyzer) checkMixedTypes(idx collector.IndexData) *finding.Finding {
	fieldTypes := make(map[string]map[string]struct{}) // field -> set of types

	for _, doc := range idx.SampleDocuments {
		collectFieldTypes(doc, "", fieldTypes)
	}

	// Find fields with mixed types (excluding int/float which is OK)
	var mixedTypeFields []string
	mixedTypeDetails := make(map[string][]string)

	for field, types := range fieldTypes {
		if len(types) > 1 {
			// Check if it's just int/float mixing (OK)
			_, hasInt := types["int"]
			_, hasFloat := types["float64"]
			if len(types) == 2 && hasInt && hasFloat {
				continue
			}

			typeList := make([]string, 0, len(types))
			for t := range types {
				typeList = append(typeList, t)
			}
			mixedTypeFields = append(mixedTypeFields, field)
			mixedTypeDetails[field] = typeList
		}
	}

	if len(mixedTypeFields) > 0 {
		return finding.New(
			"MEILI-D007",
			"Mixed types in fields",
			fmt.Sprintf("Index '%s' has fields with inconsistent types: %v. This can cause unexpected filtering behavior.", idx.UID, truncateSlice(mixedTypeFields, 3)),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Normalize field types across all documents for consistent behavior.").
			WithDetails(map[string]interface{}{
				"mixed_types": mixedTypeDetails,
			})
	}

	return nil
}

// D008: Check for very long text
func (a *DocumentAnalyzer) checkTextLength(idx collector.IndexData) *finding.Finding {
	longTextFields := make(map[string]int) // field -> max length

	for _, doc := range idx.SampleDocuments {
		findLongText(doc, "", longTextFields)
	}

	if len(longTextFields) > 0 {
		fields := make([]string, 0, len(longTextFields))
		for f := range longTextFields {
			fields = append(fields, f)
		}

		return finding.New(
			"MEILI-D008",
			"Very long text fields",
			fmt.Sprintf("Index '%s' has fields with very long text (>65535 chars): %v.", idx.UID, truncateSlice(fields, 3)),
			finding.SeveritySuggestion,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider truncating or summarizing long text for better search performance.").
			WithDetails(map[string]interface{}{
				"long_text_lengths": longTextFields,
			})
	}

	return nil
}

// D011: Check for arrays of objects
func (a *DocumentAnalyzer) checkArraysOfObjects(idx collector.IndexData) *finding.Finding {
	arrayOfObjectsFields := make(map[string]int)

	for _, doc := range idx.SampleDocuments {
		findArraysOfObjects(doc, "", arrayOfObjectsFields)
	}

	if len(arrayOfObjectsFields) == 0 {
		return nil
	}

	// Check if any are in filterable attributes
	filterable := make(map[string]struct{})
	for _, f := range idx.Settings.FilterableAttributes {
		filterable[f] = struct{}{}
	}

	var problematicFields []string
	var infoFields []string

	for field := range arrayOfObjectsFields {
		// Check if field or parent is filterable
		parts := strings.Split(field, ".")
		isFilterable := false
		for i := range parts {
			prefix := strings.Join(parts[:i+1], ".")
			if _, ok := filterable[prefix]; ok {
				isFilterable = true
				break
			}
		}
		if isFilterable {
			problematicFields = append(problematicFields, field)
		} else {
			infoFields = append(infoFields, field)
		}
	}

	if len(problematicFields) > 0 {
		return finding.New(
			"MEILI-D011",
			"Arrays of objects in filterable fields",
			fmt.Sprintf("Index '%s' has filterable fields containing arrays of objects: %v. Meilisearch flattens these, causing unexpected filter behavior.", idx.UID, truncateSlice(problematicFields, 5)),
			finding.SeverityWarning,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Consider restructuring data to avoid arrays of objects in filterable fields.").
			WithDetails(map[string]interface{}{
				"problematic_fields": problematicFields,
			})
	}

	if len(infoFields) > 0 {
		return finding.New(
			"MEILI-D011",
			"Arrays of objects detected",
			fmt.Sprintf("Index '%s' has fields containing arrays of objects: %v. Meilisearch flattens these structures.", idx.UID, truncateSlice(infoFields, 5)),
			finding.SeverityInfo,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("If you plan to filter on these fields, consider restructuring the data.").
			WithDetails(map[string]interface{}{
				"array_of_object_fields": infoFields,
			})
	}

	return nil
}

// D012: Check for geo coordinates without _geo
func (a *DocumentAnalyzer) checkGeoCoordinates(idx collector.IndexData) *finding.Finding {
	var geoCandidates []map[string]interface{}

	// Check if _geo already exists
	hasGeoField := false
	for _, doc := range idx.SampleDocuments {
		if _, exists := doc["_geo"]; exists {
			hasGeoField = true
			break
		}
	}

	if hasGeoField {
		return nil
	}

	for _, doc := range idx.SampleDocuments {
		candidates := findGeoCandidates(doc, "")
		geoCandidates = append(geoCandidates, candidates...)
	}

	if len(geoCandidates) > 0 {
		// Deduplicate by pattern
		uniquePatterns := make(map[string]map[string]interface{})
		for _, c := range geoCandidates {
			pattern, _ := c["pattern"].(string)
			if _, ok := uniquePatterns[pattern]; !ok {
				uniquePatterns[pattern] = c
			}
		}

		patterns := make([]string, 0, len(uniquePatterns))
		for p := range uniquePatterns {
			patterns = append(patterns, p)
		}

		return finding.New(
			"MEILI-D012",
			"Geo coordinates not using _geo format",
			fmt.Sprintf("Index '%s' has fields that appear to contain geo coordinates but aren't using the _geo format: %v.", idx.UID, truncateSlice(patterns, 3)),
			finding.SeveritySuggestion,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("To enable geo search, restructure coordinates to use _geo.lat and _geo.lng.").
			WithDetails(map[string]interface{}{
				"geo_candidates":     uniquePatterns,
				"recommended_format": map[string]interface{}{"_geo": map[string]float64{"lat": 45.4773, "lng": -73.6102}},
			})
	}

	return nil
}

// D013: Check for date strings that should be numeric
func (a *DocumentAnalyzer) checkDateStrings(idx collector.IndexData) *finding.Finding {
	dateStringFields := make(map[string]string) // field -> sample value

	for _, doc := range idx.SampleDocuments {
		findDateStrings(doc, "", dateStringFields)
	}

	if len(dateStringFields) == 0 {
		return nil
	}

	// Check which are sortable
	sortable := make(map[string]struct{})
	for _, s := range idx.Settings.SortableAttributes {
		sortable[s] = struct{}{}
	}

	var sortableDateFields []string
	var nonSortableDateFields []string

	for field := range dateStringFields {
		parts := strings.Split(field, ".")
		isSortable := false
		for i := range parts {
			prefix := strings.Join(parts[:i+1], ".")
			if _, ok := sortable[prefix]; ok {
				isSortable = true
				break
			}
		}
		if isSortable {
			sortableDateFields = append(sortableDateFields, field)
		} else {
			nonSortableDateFields = append(nonSortableDateFields, field)
		}
	}

	if len(sortableDateFields) > 0 {
		return finding.New(
			"MEILI-D013",
			"Date strings in sortable attributes",
			fmt.Sprintf("Index '%s' has sortable fields containing date strings: %v. String dates sort lexicographically, not chronologically.", idx.UID, truncateSlice(sortableDateFields, 3)),
			finding.SeveritySuggestion,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("Convert date strings to Unix timestamps for proper chronological sorting.").
			WithDetails(map[string]interface{}{
				"sortable_date_fields": sortableDateFields,
				"sample_values":        dateStringFields,
			})
	}

	if len(nonSortableDateFields) >= 2 {
		return finding.New(
			"MEILI-D013",
			"Date fields detected",
			fmt.Sprintf("Index '%s' has fields containing dates: %v. If sorting is needed, add to sortableAttributes and use numeric timestamps.", idx.UID, truncateSlice(nonSortableDateFields, 3)),
			finding.SeverityInfo,
			finding.CategoryDocument,
		).WithIndex(idx.UID).
			WithRecommendation("If you need to sort by dates, add them to sortableAttributes and consider using numeric timestamps.").
			WithDetails(map[string]interface{}{
				"date_fields":   nonSortableDateFields,
				"sample_values": dateStringFields,
			})
	}

	return nil
}

// Helper functions

func collectFieldNames(obj interface{}, prefix string, fields map[string]struct{}) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			fields[newPrefix] = struct{}{}
			collectFieldNames(value, newPrefix, fields)
		}
	case []interface{}:
		for _, item := range v {
			collectFieldNames(item, prefix, fields)
		}
	}
}

func scanForPII(obj interface{}, prefix string, detections map[string][]string) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			scanForPII(value, newPrefix, detections)
		}
	case []interface{}:
		for _, item := range v {
			scanForPII(item, prefix, detections)
		}
	case string:
		if len(v) >= 5 {
			for piiType, pattern := range piiPatterns {
				if pattern.MatchString(v) {
					if _, ok := detections[prefix]; !ok {
						detections[prefix] = []string{}
					}
					// Only add if not already present
					found := false
					for _, t := range detections[prefix] {
						if t == piiType {
							found = true
							break
						}
					}
					if !found {
						detections[prefix] = append(detections[prefix], piiType)
					}
				}
			}
		}
	}
}

func estimateDocSize(obj interface{}) int64 {
	// Rough estimate of JSON size
	switch v := obj.(type) {
	case map[string]interface{}:
		var size int64 = 2 // {}
		for key, value := range v {
			size += int64(len(key)) + 3 // "key":
			size += estimateDocSize(value)
		}
		return size
	case []interface{}:
		var size int64 = 2 // []
		for _, item := range v {
			size += estimateDocSize(item)
		}
		return size
	case string:
		return int64(len(v)) + 2 // quotes
	case float64, int, int64:
		return 8
	case bool:
		return 5
	case nil:
		return 4
	default:
		return 0
	}
}

func getMaxDepth(obj interface{}, currentDepth int) int {
	switch v := obj.(type) {
	case map[string]interface{}:
		if len(v) == 0 {
			return currentDepth
		}
		maxDepth := currentDepth + 1
		for _, value := range v {
			depth := getMaxDepth(value, currentDepth+1)
			if depth > maxDepth {
				maxDepth = depth
			}
		}
		return maxDepth
	case []interface{}:
		if len(v) == 0 {
			return currentDepth
		}
		maxDepth := currentDepth
		for _, item := range v {
			depth := getMaxDepth(item, currentDepth)
			if depth > maxDepth {
				maxDepth = depth
			}
		}
		return maxDepth
	default:
		return currentDepth
	}
}

func truncateSlice(slice []string, max int) []string {
	if len(slice) <= max {
		return slice
	}
	return slice[:max]
}

// collectArrayStats recursively collects array size statistics
func collectArrayStats(obj interface{}, prefix string, stats map[string][]int) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			collectArrayStats(value, newPrefix, stats)
		}
	case []interface{}:
		if prefix != "" {
			stats[prefix] = append(stats[prefix], len(v))
		}
		for _, item := range v {
			collectArrayStats(item, prefix, stats)
		}
	}
}

// findMarkupFields finds fields containing HTML or Markdown
func findMarkupFields(obj interface{}, prefix string, markupFields map[string]struct{}) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			findMarkupFields(value, newPrefix, markupFields)
		}
	case string:
		if len(v) > 10 {
			for _, pattern := range markupPatterns {
				if pattern.MatchString(v) {
					markupFields[prefix] = struct{}{}
					break
				}
			}
		}
	}
}

// countEmptyFields counts empty field occurrences
func countEmptyFields(obj interface{}, prefix string, emptyCounts, totalCounts map[string]int) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			totalCounts[newPrefix]++

			// Check if empty
			switch val := value.(type) {
			case nil:
				emptyCounts[newPrefix]++
			case string:
				if val == "" {
					emptyCounts[newPrefix]++
				}
			case []interface{}:
				if len(val) == 0 {
					emptyCounts[newPrefix]++
				} else {
					countEmptyFields(val, newPrefix, emptyCounts, totalCounts)
				}
			case map[string]interface{}:
				if len(val) == 0 {
					emptyCounts[newPrefix]++
				} else {
					countEmptyFields(val, newPrefix, emptyCounts, totalCounts)
				}
			}
		}
	case []interface{}:
		for _, item := range v {
			if m, ok := item.(map[string]interface{}); ok {
				countEmptyFields(m, prefix, emptyCounts, totalCounts)
			}
		}
	}
}

// collectFieldTypes collects types for each field
func collectFieldTypes(obj interface{}, prefix string, fieldTypes map[string]map[string]struct{}) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}

			if value != nil {
				typeName := fmt.Sprintf("%T", value)
				if _, ok := fieldTypes[newPrefix]; !ok {
					fieldTypes[newPrefix] = make(map[string]struct{})
				}
				fieldTypes[newPrefix][typeName] = struct{}{}
			}

			if m, ok := value.(map[string]interface{}); ok {
				collectFieldTypes(m, newPrefix, fieldTypes)
			}
		}
	}
}

// findLongText finds fields with very long text
func findLongText(obj interface{}, prefix string, longFields map[string]int) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			findLongText(value, newPrefix, longFields)
		}
	case string:
		if len(v) > 65535 {
			if current, ok := longFields[prefix]; !ok || len(v) > current {
				longFields[prefix] = len(v)
			}
		}
	}
}

// findArraysOfObjects finds fields that are arrays containing objects
func findArraysOfObjects(obj interface{}, prefix string, results map[string]int) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}
			findArraysOfObjects(value, newPrefix, results)
		}
	case []interface{}:
		if len(v) > 0 {
			// Check if array contains objects
			hasObjects := false
			for _, item := range v {
				if _, ok := item.(map[string]interface{}); ok {
					hasObjects = true
					break
				}
			}
			if hasObjects && prefix != "" {
				results[prefix]++
			}
			// Recurse into array items
			for _, item := range v {
				if m, ok := item.(map[string]interface{}); ok {
					findArraysOfObjects(m, prefix, results)
				}
			}
		}
	}
}

// findGeoCandidates finds fields that look like geo coordinates
func findGeoCandidates(doc map[string]interface{}, prefix string) []map[string]interface{} {
	var candidates []map[string]interface{}

	var latFields []string
	var lngFields []string

	for key, value := range doc {
		fullKey := key
		if prefix != "" {
			fullKey = prefix + "." + key
		}

		// Check if field name suggests lat
		if geoFieldPatterns[0].MatchString(key) {
			if num, ok := getNumber(value); ok && num >= -90 && num <= 90 {
				latFields = append(latFields, fullKey)
			}
		}

		// Check if field name suggests lng
		if geoFieldPatterns[1].MatchString(key) {
			if num, ok := getNumber(value); ok && num >= -180 && num <= 180 {
				lngFields = append(lngFields, fullKey)
			}
		}

		// Check for nested location objects
		if nested, ok := value.(map[string]interface{}); ok {
			// Check if this object looks like coordinates
			_, hasLat := nested["lat"]
			_, hasLng := nested["lng"]
			_, hasLatitude := nested["latitude"]
			_, hasLongitude := nested["longitude"]

			if (hasLat && hasLng) || (hasLatitude && hasLongitude) {
				candidates = append(candidates, map[string]interface{}{
					"pattern": fullKey,
					"type":    "nested_object",
					"sample":  nested,
				})
			} else {
				// Recurse
				candidates = append(candidates, findGeoCandidates(nested, fullKey)...)
			}
		}
	}

	// If we found lat/lng pairs at the same level
	if len(latFields) > 0 && len(lngFields) > 0 {
		candidates = append(candidates, map[string]interface{}{
			"pattern":   latFields[0] + "/" + lngFields[0],
			"type":      "separate_fields",
			"lat_field": latFields[0],
			"lng_field": lngFields[0],
		})
	}

	return candidates
}

// getNumber extracts a numeric value from an interface
func getNumber(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	default:
		return 0, false
	}
}

// findDateStrings finds string fields that contain date-like values
func findDateStrings(obj interface{}, prefix string, results map[string]string) {
	switch v := obj.(type) {
	case map[string]interface{}:
		for key, value := range v {
			newPrefix := key
			if prefix != "" {
				newPrefix = prefix + "." + key
			}

			if str, ok := value.(string); ok && len(str) >= 8 && len(str) <= 30 {
				// Check if field name suggests date
				isDateField := false
				for _, pattern := range dateFieldPatterns {
					if pattern.MatchString(key) {
						isDateField = true
						break
					}
				}

				// Check if value looks like a date
				isDateValue := false
				for _, pattern := range datePatterns {
					if pattern.MatchString(str) {
						isDateValue = true
						break
					}
				}

				if isDateField || isDateValue {
					if _, ok := results[newPrefix]; !ok {
						results[newPrefix] = str
					}
				}
			} else if nested, ok := value.(map[string]interface{}); ok {
				findDateStrings(nested, newPrefix, results)
			} else if arr, ok := value.([]interface{}); ok {
				for _, item := range arr {
					if m, ok := item.(map[string]interface{}); ok {
						findDateStrings(m, newPrefix, results)
					}
				}
			}
		}
	}
}
