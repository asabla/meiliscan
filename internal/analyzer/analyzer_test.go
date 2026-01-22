package analyzer

import (
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

func TestNewRegistry(t *testing.T) {
	r := NewRegistry()

	if r == nil {
		t.Fatal("expected registry to be created")
	}

	// Should have default analyzers registered
	if len(r.analyzers) == 0 {
		t.Error("expected default analyzers to be registered")
	}

	// Verify we have at least the core analyzers
	expectedCount := 5 // Schema, Performance, Document, Instance, BestPractices
	if len(r.analyzers) != expectedCount {
		t.Errorf("expected %d default analyzers, got %d", expectedCount, len(r.analyzers))
	}
}

func TestRegistry_Register(t *testing.T) {
	r := &Registry{}

	// Start empty
	if len(r.analyzers) != 0 {
		t.Fatalf("expected empty registry, got %d analyzers", len(r.analyzers))
	}

	// Register a mock analyzer
	mock := &mockAnalyzer{name: "test"}
	r.Register(mock)

	if len(r.analyzers) != 1 {
		t.Errorf("expected 1 analyzer after Register, got %d", len(r.analyzers))
	}

	// Register another
	r.Register(&mockAnalyzer{name: "test2"})
	if len(r.analyzers) != 2 {
		t.Errorf("expected 2 analyzers, got %d", len(r.analyzers))
	}
}

func TestRegistry_Analyze(t *testing.T) {
	r := &Registry{}

	// Register mock analyzers that return known findings
	r.Register(&mockAnalyzer{
		name: "mock1",
		findings: []*finding.Finding{
			finding.New("MOCK-001", "Finding 1", "Desc", finding.SeverityWarning, finding.CategoryPerformance),
		},
	})
	r.Register(&mockAnalyzer{
		name: "mock2",
		findings: []*finding.Finding{
			finding.New("MOCK-002", "Finding 2", "Desc", finding.SeverityCritical, finding.CategorySchema),
			finding.New("MOCK-003", "Finding 3", "Desc", finding.SeverityInfo, finding.CategoryDocument),
		},
	})

	data := &collector.CollectedData{
		SourceType: "test",
	}

	findings := r.Analyze(data)

	// Should combine findings from all analyzers
	if len(findings) != 3 {
		t.Errorf("expected 3 combined findings, got %d", len(findings))
	}

	// Verify all IDs present
	ids := make(map[string]bool)
	for _, f := range findings {
		ids[f.ID] = true
	}

	for _, expectedID := range []string{"MOCK-001", "MOCK-002", "MOCK-003"} {
		if !ids[expectedID] {
			t.Errorf("expected finding %s not found", expectedID)
		}
	}
}

func TestRegistry_Analyze_EmptyRegistry(t *testing.T) {
	r := &Registry{}

	data := &collector.CollectedData{
		SourceType: "test",
	}

	findings := r.Analyze(data)

	if len(findings) != 0 {
		t.Errorf("expected 0 findings from empty registry, got %d", len(findings))
	}
}

func TestRegistry_Analyze_Integration(t *testing.T) {
	// Test with real registry and realistic data
	r := NewRegistry()

	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		Version:    "1.12.0",
		Indexes: []collector.IndexData{
			{
				UID:               "movies",
				PrimaryKey:        "id",
				NumberOfDocuments: 1000,
				Settings: &collector.IndexSettings{
					SearchableAttributes: []string{"*"},
					FilterableAttributes: []string{},
					SortableAttributes:   []string{},
					RankingRules:         []string{"words", "typo", "proximity", "attribute", "sort", "exactness"},
				},
				SampleDocuments: []map[string]interface{}{
					{"id": 1, "title": "Test Movie", "year": 2020},
					{"id": 2, "title": "Another Movie", "year": 2021},
				},
			},
		},
		InstanceInfo: &collector.InstanceInfo{
			HasMasterKey: true,
		},
	}

	findings := r.Analyze(data)

	// Should have some findings (at minimum S002 for empty filterable)
	t.Logf("Integration test found %d findings", len(findings))
	for _, f := range findings {
		t.Logf("  - %s: %s (%s)", f.ID, f.Title, f.Severity)
	}

	// Verify findings are properly formed
	for _, f := range findings {
		if f.ID == "" {
			t.Error("finding has empty ID")
		}
		if f.Title == "" {
			t.Error("finding has empty Title")
		}
		if f.Severity == "" {
			t.Error("finding has empty Severity")
		}
	}
}

func TestRegistry_Analyze_WithNoAuth(t *testing.T) {
	// Test that I001 (no authentication) is detected
	r := NewRegistry()

	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		InstanceInfo: &collector.InstanceInfo{
			HasMasterKey: false, // No auth!
		},
		Indexes: []collector.IndexData{},
	}

	findings := r.Analyze(data)

	// Should find I001
	found := false
	for _, f := range findings {
		if f.ID == "MEILI-I001" {
			found = true
			if f.Severity != finding.SeverityCritical {
				t.Errorf("I001 should be critical, got %s", f.Severity)
			}
			break
		}
	}

	if !found {
		t.Error("expected MEILI-I001 (no authentication) finding")
	}
}

// mockAnalyzer is a test helper
type mockAnalyzer struct {
	name     string
	findings []*finding.Finding
}

func (m *mockAnalyzer) Name() string {
	return m.name
}

func (m *mockAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	return m.findings
}
