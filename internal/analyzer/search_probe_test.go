package analyzer

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

func TestSearchProbeAnalyzer_Name(t *testing.T) {
	probe := NewSearchProbeAnalyzer(nil)
	if probe.Name() != "search_probe" {
		t.Errorf("expected name 'search_probe', got %q", probe.Name())
	}
}

func TestSearchProbeAnalyzer_NilCollector(t *testing.T) {
	probe := NewSearchProbeAnalyzer(nil)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID: "test",
				Settings: &collector.IndexSettings{
					SortableAttributes:   []string{"price"},
					FilterableAttributes: []string{"category"},
				},
			},
		},
	}

	findings := probe.Analyze(data)
	if findings != nil {
		t.Errorf("expected nil findings with nil collector, got %d", len(findings))
	}
}

func TestSearchProbeAnalyzer_DumpFile(t *testing.T) {
	// Create a mock server (won't be called)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("server should not be called for dump files")
	}))
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "dump", // Not live
		Indexes: []collector.IndexData{
			{
				UID: "test",
				Settings: &collector.IndexSettings{
					SortableAttributes: []string{"price"},
				},
			},
		},
	}

	findings := probe.Analyze(data)
	if len(findings) > 0 {
		t.Errorf("expected no findings for dump file, got %d", len(findings))
	}
}

func TestSearchProbeAnalyzer_NoSettings(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:      "test",
				Settings: nil, // No settings
			},
		},
	}

	findings := probe.Analyze(data)
	if len(findings) != 0 {
		t.Errorf("expected no findings for index without settings, got %d", len(findings))
	}
}

func TestSearchProbeAnalyzer_BasicSearch_Success(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{
		searchResponse: map[string]interface{}{
			"hits":             []map[string]interface{}{{"id": 1, "title": "Test"}},
			"query":            "",
			"processingTimeMs": 5,
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "movies",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					SearchableAttributes: []string{"title"},
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// No findings expected for successful small response
	for _, f := range findings {
		if f.ID == "MEILI-Q003" {
			t.Errorf("unexpected large response finding for small response")
		}
	}
}

func TestSearchProbeAnalyzer_BasicSearch_LargeResponse(t *testing.T) {
	// Create a large response (> 100KB)
	largeHits := make([]map[string]interface{}, 100)
	for i := 0; i < 100; i++ {
		largeHits[i] = map[string]interface{}{
			"id":          i,
			"title":       strings.Repeat("A", 500),
			"description": strings.Repeat("B", 1000),
		}
	}

	server := createMockMeilisearchServer(t, mockServerConfig{
		searchResponse: map[string]interface{}{
			"hits":             largeHits,
			"query":            "",
			"processingTimeMs": 50,
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "movies",
				NumberOfDocuments: 1000,
				Settings: &collector.IndexSettings{
					SearchableAttributes: []string{"title", "description"},
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// Should find Q003 (large response)
	found := false
	for _, f := range findings {
		if f.ID == "MEILI-Q003" {
			found = true
			if f.Severity != finding.SeverityInfo {
				t.Errorf("Q003 should be info severity, got %s", f.Severity)
			}
			break
		}
	}

	if !found {
		t.Error("expected MEILI-Q003 (large response) finding")
	}
}

func TestSearchProbeAnalyzer_SortProbe_Success(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{
		searchResponse: map[string]interface{}{
			"hits":             []map[string]interface{}{{"id": 1}},
			"query":            "",
			"processingTimeMs": 5,
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "products",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					SortableAttributes: []string{"price", "rating"},
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// No Q001 findings expected for successful sort
	for _, f := range findings {
		if f.ID == "MEILI-Q001" {
			t.Errorf("unexpected sort failure finding")
		}
	}
}

func TestSearchProbeAnalyzer_SortProbe_Failure(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{
		searchError: &mockError{
			code:    http.StatusBadRequest,
			message: "invalid_sort_field",
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "products",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					SortableAttributes: []string{"invalid_field"},
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// Should find Q001 (sort failure)
	found := false
	for _, f := range findings {
		if f.ID == "MEILI-Q001" {
			found = true
			if f.Severity != finding.SeverityWarning {
				t.Errorf("Q001 should be warning severity, got %s", f.Severity)
			}
			break
		}
	}

	if !found {
		t.Error("expected MEILI-Q001 (sort failure) finding")
	}
}

func TestSearchProbeAnalyzer_FilterProbe_Success(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{
		searchResponse: map[string]interface{}{
			"hits":             []map[string]interface{}{{"id": 1, "category": "electronics"}},
			"query":            "",
			"processingTimeMs": 5,
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "products",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					FilterableAttributes: []string{"category"},
				},
				SampleDocuments: []map[string]interface{}{
					{"id": 1, "category": "electronics"},
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// No Q002 findings expected for successful filter
	for _, f := range findings {
		if f.ID == "MEILI-Q002" {
			t.Errorf("unexpected filter failure finding")
		}
	}
}

func TestSearchProbeAnalyzer_FilterProbe_Failure(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{
		searchError: &mockError{
			code:    http.StatusBadRequest,
			message: "invalid_filter",
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "products",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					FilterableAttributes: []string{"category"},
				},
				SampleDocuments: []map[string]interface{}{
					{"id": 1, "category": "electronics"},
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// Should find Q002 (filter failure)
	found := false
	for _, f := range findings {
		if f.ID == "MEILI-Q002" {
			found = true
			if f.Severity != finding.SeverityWarning {
				t.Errorf("Q002 should be warning severity, got %s", f.Severity)
			}
			break
		}
	}

	if !found {
		t.Error("expected MEILI-Q002 (filter failure) finding")
	}
}

func TestSearchProbeAnalyzer_FilterProbe_NoSampleValue(t *testing.T) {
	server := createMockMeilisearchServer(t, mockServerConfig{
		searchResponse: map[string]interface{}{
			"hits":             []map[string]interface{}{},
			"query":            "",
			"processingTimeMs": 5,
		},
	})
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "products",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					FilterableAttributes: []string{"category"},
				},
				SampleDocuments: []map[string]interface{}{
					{"id": 1}, // No category field
				},
			},
		},
	}

	findings := probe.Analyze(data)

	// Should not have filter findings (no value to test with)
	for _, f := range findings {
		if f.ID == "MEILI-Q002" {
			t.Errorf("unexpected filter finding when no sample value available")
		}
	}
}

func TestFindFilterValue(t *testing.T) {
	probe := NewSearchProbeAnalyzer(nil)

	tests := []struct {
		name     string
		idx      collector.IndexData
		field    string
		expected interface{}
	}{
		{
			name: "string value",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"category": "electronics"},
				},
			},
			field:    "category",
			expected: "electronics",
		},
		{
			name: "number value",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"price": 99.99},
				},
			},
			field:    "price",
			expected: 99.99,
		},
		{
			name: "bool value",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"active": true},
				},
			},
			field:    "active",
			expected: true,
		},
		{
			name: "skip array",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"tags": []interface{}{"a", "b"}},
				},
			},
			field:    "tags",
			expected: nil,
		},
		{
			name: "skip object",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"meta": map[string]interface{}{"key": "value"}},
				},
			},
			field:    "meta",
			expected: nil,
		},
		{
			name: "field not found",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"other": "value"},
				},
			},
			field:    "missing",
			expected: nil,
		},
		{
			name: "nil value skipped",
			idx: collector.IndexData{
				SampleDocuments: []map[string]interface{}{
					{"field": nil},
					{"field": "actual"},
				},
			},
			field:    "field",
			expected: "actual",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := probe.findFilterValue(tt.idx, tt.field)
			if result != tt.expected {
				t.Errorf("expected %v, got %v", tt.expected, result)
			}
		})
	}
}

func TestFindingsFromProbes(t *testing.T) {
	probe := NewSearchProbeAnalyzer(nil)
	idx := collector.IndexData{UID: "test"}

	tests := []struct {
		name           string
		probes         []ProbeResult
		expectedIDs    []string
		notExpectedIDs []string
	}{
		{
			name: "sort failure generates Q001",
			probes: []ProbeResult{
				{ProbeType: "sort", Field: "price", Success: false, ErrorMessage: "invalid"},
			},
			expectedIDs: []string{"MEILI-Q001"},
		},
		{
			name: "filter failure generates Q002",
			probes: []ProbeResult{
				{ProbeType: "filter", Field: "category", Success: false, ErrorMessage: "invalid"},
			},
			expectedIDs: []string{"MEILI-Q002"},
		},
		{
			name: "large response generates Q003",
			probes: []ProbeResult{
				{ProbeType: "basic", Success: true, ResponseSizeBytes: 150 * 1024, HitCount: 50},
			},
			expectedIDs: []string{"MEILI-Q003"},
		},
		{
			name: "small response no Q003",
			probes: []ProbeResult{
				{ProbeType: "basic", Success: true, ResponseSizeBytes: 10 * 1024, HitCount: 10},
			},
			notExpectedIDs: []string{"MEILI-Q003"},
		},
		{
			name: "successful sort no Q001",
			probes: []ProbeResult{
				{ProbeType: "sort", Field: "price", Success: true},
			},
			notExpectedIDs: []string{"MEILI-Q001"},
		},
		{
			name: "successful filter no Q002",
			probes: []ProbeResult{
				{ProbeType: "filter", Field: "category", Success: true},
			},
			notExpectedIDs: []string{"MEILI-Q002"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			findings := probe.findingsFromProbes(idx, tt.probes)

			foundIDs := make(map[string]bool)
			for _, f := range findings {
				foundIDs[f.ID] = true
			}

			for _, expectedID := range tt.expectedIDs {
				if !foundIDs[expectedID] {
					t.Errorf("expected finding %s not found", expectedID)
				}
			}

			for _, notExpectedID := range tt.notExpectedIDs {
				if foundIDs[notExpectedID] {
					t.Errorf("unexpected finding %s found", notExpectedID)
				}
			}
		})
	}
}

func TestSearchProbeAnalyzer_MaxProbesLimit(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		json.NewEncoder(w).Encode(map[string]interface{}{
			"hits":             []map[string]interface{}{},
			"query":            "",
			"processingTimeMs": 1,
		})
	}))
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	// Create index with many sortable/filterable to test limit
	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "test",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					SortableAttributes:   []string{"a", "b", "c", "d", "e"},
					FilterableAttributes: []string{"f", "g", "h", "i", "j"},
				},
				SampleDocuments: []map[string]interface{}{
					{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": "x", "g": "y", "h": "z", "i": "w", "j": "v"},
				},
			},
		},
	}

	probe.Analyze(data)

	// Should be limited to MaxProbesPerIndex (5)
	if requestCount > MaxProbesPerIndex {
		t.Errorf("expected max %d probes, got %d", MaxProbesPerIndex, requestCount)
	}
}

func TestSearchProbeAnalyzer_FilterValueTypes(t *testing.T) {
	// Test different filter value types in probeFilter
	responses := make(chan map[string]interface{}, 10)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"hits":             []map[string]interface{}{},
			"query":            "",
			"processingTimeMs": 1,
		})
	}))
	defer server.Close()

	coll := collector.NewLiveCollector(server.URL, "")
	probe := NewSearchProbeAnalyzer(coll)

	// Test with different value types
	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{
				UID:               "test",
				NumberOfDocuments: 100,
				Settings: &collector.IndexSettings{
					FilterableAttributes: []string{"str_field", "bool_field", "int_field", "float_field"},
				},
				SampleDocuments: []map[string]interface{}{
					{
						"str_field":   "hello",
						"bool_field":  true,
						"int_field":   float64(42), // JSON numbers are float64
						"float_field": 3.14,
					},
				},
			},
		},
	}

	// Should not panic with different types
	findings := probe.Analyze(data)
	_ = findings
	close(responses)
}

// Helper types and functions for mock server

type mockError struct {
	code    int
	message string
}

type mockServerConfig struct {
	searchResponse map[string]interface{}
	searchError    *mockError
}

func createMockMeilisearchServer(t *testing.T, config mockServerConfig) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Handle search requests
		if strings.Contains(r.URL.Path, "/search") {
			if config.searchError != nil {
				w.WriteHeader(config.searchError.code)
				json.NewEncoder(w).Encode(map[string]interface{}{
					"message": config.searchError.message,
					"code":    "invalid_request",
				})
				return
			}

			if config.searchResponse != nil {
				json.NewEncoder(w).Encode(config.searchResponse)
				return
			}

			// Default response
			json.NewEncoder(w).Encode(map[string]interface{}{
				"hits":             []map[string]interface{}{},
				"query":            "",
				"processingTimeMs": 1,
			})
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
}
