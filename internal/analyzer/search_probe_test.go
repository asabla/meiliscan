package analyzer

import (
	"context"
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/collector"
)

// TestSearchProbeAnalyzer_LiveInstance tests probing against a live Meilisearch instance.
// This test requires a Meilisearch instance running at localhost:7700.
// Skip this test if no instance is available.
func TestSearchProbeAnalyzer_LiveInstance(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Try to connect to local Meilisearch
	coll := collector.NewLiveCollector("http://localhost:7700", "")

	data, err := coll.Collect(ctx)
	if err != nil {
		t.Skipf("Skipping test - no Meilisearch at localhost:7700: %v", err)
	}

	t.Logf("Source type: %s", data.SourceType)
	t.Logf("Found %d indexes", len(data.Indexes))

	for _, idx := range data.Indexes {
		t.Logf("Index %s:", idx.UID)
		t.Logf("  - Sample docs: %d", len(idx.SampleDocuments))
		t.Logf("  - Number of docs: %d", idx.NumberOfDocuments)
		if idx.Settings != nil {
			t.Logf("  - Sortable: %v", idx.Settings.SortableAttributes)
			t.Logf("  - Filterable: %v", idx.Settings.FilterableAttributes)
		}

		// Test basic search directly
		resp, err := coll.Search(ctx, idx.UID, collector.SearchRequest{
			Query: "",
			Limit: 50,
		})
		if err != nil {
			t.Logf("  - Search error: %v", err)
		} else {
			t.Logf("  - Search response size: %d bytes (%.1f KB)", len(resp.RawResponse), float64(len(resp.RawResponse))/1024)
			t.Logf("  - Hits: %d", len(resp.Hits))
		}
	}

	// Create probe analyzer
	probe := NewSearchProbeAnalyzer(coll)
	findings := probe.Analyze(data)

	t.Logf("Probe findings: %d", len(findings))
	for _, f := range findings {
		t.Logf("  - %s: %s", f.ID, f.Title)
	}

	// The test passes regardless of findings - we just want to verify it runs
}

// TestSearchProbeAnalyzer_MockData tests the probe analyzer with mock data.
func TestSearchProbeAnalyzer_MockData(t *testing.T) {
	// Test without a collector (should return nil)
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
		t.Errorf("Expected nil findings with nil collector, got %d", len(findings))
	}
}

// TestSearchProbeAnalyzer_DumpFile tests that probe analyzer skips dump files.
func TestSearchProbeAnalyzer_DumpFile(t *testing.T) {
	coll := collector.NewLiveCollector("http://localhost:7700", "")
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
		t.Errorf("Expected no findings for dump file, got %d", len(findings))
	}
}
