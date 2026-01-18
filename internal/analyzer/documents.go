package analyzer

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

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
