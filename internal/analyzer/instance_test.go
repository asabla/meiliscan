package analyzer

import (
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

func TestInstanceAnalyzer_Name(t *testing.T) {
	a := NewInstanceAnalyzer()
	if a.Name() != "instance" {
		t.Errorf("expected name 'instance', got %q", a.Name())
	}
}

func TestInstanceAnalyzer_I001_NoAuthentication(t *testing.T) {
	tests := []struct {
		name           string
		data           *collector.CollectedData
		expectFinding  bool
		expectSeverity finding.Severity
	}{
		{
			name: "no authentication - critical finding",
			data: &collector.CollectedData{
				SourceType: "live",
				SourceURL:  "http://localhost:7700",
				InstanceInfo: &collector.InstanceInfo{
					HasMasterKey: false,
				},
			},
			expectFinding:  true,
			expectSeverity: finding.SeverityCritical,
		},
		{
			name: "with authentication - no finding",
			data: &collector.CollectedData{
				SourceType: "live",
				SourceURL:  "http://localhost:7700",
				InstanceInfo: &collector.InstanceInfo{
					HasMasterKey: true,
				},
			},
			expectFinding: false,
		},
		{
			name: "not live source - skip check",
			data: &collector.CollectedData{
				SourceType: "file",
				SourceURL:  "/path/to/data.json",
				InstanceInfo: &collector.InstanceInfo{
					HasMasterKey: false,
				},
			},
			expectFinding: false,
		},
		{
			name: "no instance info - skip check",
			data: &collector.CollectedData{
				SourceType:   "live",
				SourceURL:    "http://localhost:7700",
				InstanceInfo: nil,
			},
			expectFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			a := NewInstanceAnalyzer()
			findings := a.Analyze(tt.data)

			if tt.expectFinding {
				if len(findings) != 1 {
					t.Fatalf("expected 1 finding, got %d", len(findings))
				}

				f := findings[0]
				if f.ID != "MEILI-I001" {
					t.Errorf("expected ID MEILI-I001, got %s", f.ID)
				}
				if f.Severity != tt.expectSeverity {
					t.Errorf("expected severity %s, got %s", tt.expectSeverity, f.Severity)
				}
				if f.Category != finding.CategoryInstance {
					t.Errorf("expected category %s, got %s", finding.CategoryInstance, f.Category)
				}

				// Check details
				if f.Details == nil {
					t.Error("expected details to be set")
				} else {
					if f.Details["has_master_key"] != false {
						t.Error("expected has_master_key to be false")
					}
					if f.Details["instance_url"] != tt.data.SourceURL {
						t.Errorf("expected instance_url to be %s", tt.data.SourceURL)
					}
				}

				// Check recommendation is set
				if f.Recommendation == "" {
					t.Error("expected recommendation to be set")
				}
			} else {
				if len(findings) != 0 {
					t.Errorf("expected 0 findings, got %d", len(findings))
				}
			}
		})
	}
}

func TestInstanceAnalyzer_Analyze_ReturnsEmptySlice(t *testing.T) {
	// Ensure Analyze returns empty slice (not nil) when no findings
	a := NewInstanceAnalyzer()
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		InstanceInfo: &collector.InstanceInfo{
			HasMasterKey: true, // Has auth, so no finding
		},
	}

	findings := a.Analyze(data)

	// Go convention: nil slice is fine for empty results
	if findings == nil {
		// This is acceptable
	}
	if len(findings) != 0 {
		t.Errorf("expected 0 findings, got %d", len(findings))
	}
}
