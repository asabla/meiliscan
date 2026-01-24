package analyzer

import (
	"context"
	"fmt"
	"time"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// MaxResponseSize is the threshold for large response warnings (100KB)
const MaxResponseSize = 100 * 1024

// MaxProbesPerIndex limits the number of probes per index
const MaxProbesPerIndex = 5

// ProbeResult holds the result of a search probe.
type ProbeResult struct {
	IndexUID          string
	ProbeType         string // "sort", "filter", "basic"
	Field             string
	Success           bool
	ErrorMessage      string
	ResponseSizeBytes int
	HitCount          int
}

// SearchProbeAnalyzer validates index configuration by running test queries.
type SearchProbeAnalyzer struct {
	collector *collector.LiveCollector
}

// NewSearchProbeAnalyzer creates a new SearchProbeAnalyzer.
func NewSearchProbeAnalyzer(coll *collector.LiveCollector) *SearchProbeAnalyzer {
	return &SearchProbeAnalyzer{
		collector: coll,
	}
}

// Name returns the analyzer name.
func (a *SearchProbeAnalyzer) Name() string {
	return "search_probe"
}

// Analyze runs search probes and returns findings.
// Note: This analyzer requires a live collector and won't work with dump files.
func (a *SearchProbeAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	if a.collector == nil {
		return nil
	}

	// Only run on live instances
	if data.SourceType != "live" {
		return nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	var findings []*finding.Finding

	for _, idx := range data.Indexes {
		if idx.Settings == nil {
			continue
		}

		probeResults := a.probeIndex(ctx, idx)
		findings = append(findings, a.findingsFromProbes(idx, probeResults)...)
	}

	return findings
}

// probeIndex runs probes against a single index.
func (a *SearchProbeAnalyzer) probeIndex(ctx context.Context, idx collector.IndexData) []ProbeResult {
	var results []ProbeResult
	probeCount := 0

	// Basic search probe (empty query) - always run first
	if probeCount < MaxProbesPerIndex {
		result := a.probeBasicSearch(ctx, idx)
		results = append(results, result)
		probeCount++
	}

	// Sort probes - test up to 2 sortable attributes
	sortableToTest := idx.Settings.SortableAttributes
	if len(sortableToTest) > 2 {
		sortableToTest = sortableToTest[:2]
	}
	for _, field := range sortableToTest {
		if probeCount >= MaxProbesPerIndex {
			break
		}
		result := a.probeSort(ctx, idx, field)
		results = append(results, result)
		probeCount++
	}

	// Filter probes - test up to 2 filterable attributes
	filterableToTest := idx.Settings.FilterableAttributes
	if len(filterableToTest) > 2 {
		filterableToTest = filterableToTest[:2]
	}
	for _, field := range filterableToTest {
		if probeCount >= MaxProbesPerIndex {
			break
		}
		// Find a value to filter on from sample documents
		value := a.findFilterValue(idx, field)
		if value != nil {
			result := a.probeFilter(ctx, idx, field, value)
			results = append(results, result)
			probeCount++
		}
	}

	return results
}

// probeBasicSearch tests a basic empty query.
func (a *SearchProbeAnalyzer) probeBasicSearch(ctx context.Context, idx collector.IndexData) ProbeResult {
	// Use a moderate limit to get a realistic sample of response size
	// Meilisearch default is 20, but we use 50 to better detect large responses
	limit := 50
	if idx.NumberOfDocuments < 50 {
		limit = int(idx.NumberOfDocuments)
		if limit < 1 {
			limit = 20 // fallback
		}
	}

	resp, err := a.collector.Search(ctx, idx.UID, collector.SearchRequest{
		Query: "",
		Limit: limit,
	})

	if err != nil {
		return ProbeResult{
			IndexUID:     idx.UID,
			ProbeType:    "basic",
			Success:      false,
			ErrorMessage: err.Error(),
		}
	}

	return ProbeResult{
		IndexUID:          idx.UID,
		ProbeType:         "basic",
		Success:           true,
		ResponseSizeBytes: len(resp.RawResponse),
		HitCount:          len(resp.Hits),
	}
}

// probeSort tests sorting by a field.
func (a *SearchProbeAnalyzer) probeSort(ctx context.Context, idx collector.IndexData, field string) ProbeResult {
	_, err := a.collector.Search(ctx, idx.UID, collector.SearchRequest{
		Query: "",
		Sort:  []string{field + ":asc"},
		Limit: 1,
	})

	if err != nil {
		return ProbeResult{
			IndexUID:     idx.UID,
			ProbeType:    "sort",
			Field:        field,
			Success:      false,
			ErrorMessage: err.Error(),
		}
	}

	return ProbeResult{
		IndexUID:  idx.UID,
		ProbeType: "sort",
		Field:     field,
		Success:   true,
	}
}

// probeFilter tests filtering by a field.
func (a *SearchProbeAnalyzer) probeFilter(ctx context.Context, idx collector.IndexData, field string, value interface{}) ProbeResult {
	// Build filter expression based on value type
	var filterExpr string
	switch v := value.(type) {
	case string:
		filterExpr = fmt.Sprintf(`%s = "%s"`, field, v)
	case bool:
		filterExpr = fmt.Sprintf(`%s = %t`, field, v)
	case float64:
		// Check if it's actually an integer
		if v == float64(int64(v)) {
			filterExpr = fmt.Sprintf(`%s = %d`, field, int64(v))
		} else {
			filterExpr = fmt.Sprintf(`%s = %f`, field, v)
		}
	default:
		filterExpr = fmt.Sprintf(`%s = "%v"`, field, v)
	}

	_, err := a.collector.Search(ctx, idx.UID, collector.SearchRequest{
		Query:  "",
		Filter: filterExpr,
		Limit:  1,
	})

	if err != nil {
		return ProbeResult{
			IndexUID:     idx.UID,
			ProbeType:    "filter",
			Field:        field,
			Success:      false,
			ErrorMessage: err.Error(),
		}
	}

	return ProbeResult{
		IndexUID:  idx.UID,
		ProbeType: "filter",
		Field:     field,
		Success:   true,
	}
}

// findFilterValue finds a sample value for a field from sample documents.
func (a *SearchProbeAnalyzer) findFilterValue(idx collector.IndexData, field string) interface{} {
	for _, doc := range idx.SampleDocuments {
		if val, exists := doc[field]; exists && val != nil {
			// Skip arrays and objects - we want simple values
			switch val.(type) {
			case []interface{}, map[string]interface{}:
				continue
			default:
				return val
			}
		}
	}
	return nil
}

// findingsFromProbes generates findings from probe results.
func (a *SearchProbeAnalyzer) findingsFromProbes(idx collector.IndexData, probeResults []ProbeResult) []*finding.Finding {
	var findings []*finding.Finding

	for _, result := range probeResults {
		switch result.ProbeType {
		case "sort":
			if !result.Success {
				// Q001: Sort probe failed
				findings = append(findings, finding.New(
					"MEILI-Q001",
					fmt.Sprintf("Sort on '%s' failed", result.Field),
					fmt.Sprintf("Attempting to sort by '%s' on index '%s' returned an error. This field is configured as sortable but may have incompatible data types or other issues. Error: %s",
						result.Field, idx.UID, result.ErrorMessage),
					finding.SeverityWarning,
					finding.CategorySearchProbe,
				).WithIndex(idx.UID).
					WithRecommendation("Verify the field contains sortable data types (numbers, strings, dates). Check for null values or mixed types that may cause sorting issues.").
					WithDetails(map[string]interface{}{
						"field": result.Field,
						"error": result.ErrorMessage,
					}))
			}

		case "filter":
			if !result.Success {
				// Q002: Filter probe failed
				findings = append(findings, finding.New(
					"MEILI-Q002",
					fmt.Sprintf("Filter on '%s' failed", result.Field),
					fmt.Sprintf("Attempting to filter by '%s' on index '%s' returned an error. This field is configured as filterable but may have incompatible data or syntax issues. Error: %s",
						result.Field, idx.UID, result.ErrorMessage),
					finding.SeverityWarning,
					finding.CategorySearchProbe,
				).WithIndex(idx.UID).
					WithRecommendation("Verify the field contains filterable data types. Check for issues with the filter syntax or incompatible values.").
					WithDetails(map[string]interface{}{
						"field": result.Field,
						"error": result.ErrorMessage,
					}))
			}

		case "basic":
			if result.Success && result.ResponseSizeBytes > MaxResponseSize {
				// Q003: Large response payload
				sizeKB := float64(result.ResponseSizeBytes) / 1024
				findings = append(findings, finding.New(
					"MEILI-Q003",
					"Large search response payload",
					fmt.Sprintf("A basic search on index '%s' returned a response of %.1f KB. Large responses increase bandwidth usage and may slow down client applications.",
						idx.UID, sizeKB),
					finding.SeverityInfo,
					finding.CategorySearchProbe,
				).WithIndex(idx.UID).
					WithRecommendation("Consider limiting displayedAttributes to only the fields needed for search results, or reducing the default hit limit.").
					WithDetails(map[string]interface{}{
						"response_size_bytes": result.ResponseSizeBytes,
						"response_size_kb":    sizeKB,
						"hit_count":           result.HitCount,
						"threshold_kb":        MaxResponseSize / 1024,
					}))
			}
		}
	}

	return findings
}
