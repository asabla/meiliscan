package exporter

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

func TestSARIFExporter_Export(t *testing.T) {
	r := &report.Report{
		GeneratedAt: time.Date(2024, 1, 15, 10, 0, 0, 0, time.UTC),
		Source: report.Source{
			Type: "live",
			URL:  "http://localhost:7700",
		},
		Findings: []*finding.Finding{
			{
				ID:             "MEILI-S001",
				Title:          "No primary key set",
				Description:    "Index 'movies' has no primary key configured.",
				Severity:       finding.SeverityWarning,
				Category:       finding.CategorySchema,
				IndexUID:       "movies",
				Recommendation: "Set a primary key for the index.",
				Details: map[string]interface{}{
					"index": "movies",
				},
			},
			{
				ID:          "MEILI-I001",
				Title:       "Instance without authentication",
				Description: "Meilisearch instance is accessible without authentication.",
				Severity:    finding.SeverityCritical,
				Category:    finding.CategoryInstance,
			},
		},
	}

	exporter := NewSARIF()
	output, err := exporter.Export(r)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	// Parse the output to verify structure
	var sarif sarifLog
	if err := json.Unmarshal(output, &sarif); err != nil {
		t.Fatalf("Output is not valid JSON: %v", err)
	}

	// Verify schema
	if sarif.Schema != "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json" {
		t.Errorf("unexpected schema: %s", sarif.Schema)
	}

	// Verify version
	if sarif.Version != "2.1.0" {
		t.Errorf("unexpected version: %s", sarif.Version)
	}

	// Verify runs
	if len(sarif.Runs) != 1 {
		t.Fatalf("expected 1 run, got %d", len(sarif.Runs))
	}

	run := sarif.Runs[0]

	// Verify tool info
	if run.Tool.Driver.Name != "meiliscan" {
		t.Errorf("unexpected tool name: %s", run.Tool.Driver.Name)
	}

	// Verify rules (should have 2 unique rules)
	if len(run.Tool.Driver.Rules) != 2 {
		t.Errorf("expected 2 rules, got %d", len(run.Tool.Driver.Rules))
	}

	// Verify results
	if len(run.Results) != 2 {
		t.Errorf("expected 2 results, got %d", len(run.Results))
	}

	// Check first result (warning)
	foundWarning := false
	foundError := false
	for _, result := range run.Results {
		if result.RuleID == "MEILI-S001" {
			foundWarning = true
			if result.Level != "warning" {
				t.Errorf("expected warning level for S001, got %s", result.Level)
			}
			if len(result.Locations) == 0 {
				t.Error("expected locations for index-specific finding")
			} else if len(result.Locations[0].LogicalLocations) == 0 {
				t.Error("expected logical location for index-specific finding")
			} else if result.Locations[0].LogicalLocations[0].Name != "movies" {
				t.Errorf("expected logical location name 'movies', got %s", result.Locations[0].LogicalLocations[0].Name)
			}
			if len(result.Fixes) == 0 {
				t.Error("expected fix for finding with recommendation")
			}
		}
		if result.RuleID == "MEILI-I001" {
			foundError = true
			if result.Level != "error" {
				t.Errorf("expected error level for critical severity, got %s", result.Level)
			}
		}
	}

	if !foundWarning {
		t.Error("warning result not found")
	}
	if !foundError {
		t.Error("error result not found")
	}
}

func TestSARIFExporter_SeverityMapping(t *testing.T) {
	exporter := NewSARIF()

	tests := []struct {
		severity finding.Severity
		expected string
	}{
		{finding.SeverityCritical, "error"},
		{finding.SeverityWarning, "warning"},
		{finding.SeveritySuggestion, "note"},
		{finding.SeverityInfo, "note"},
	}

	for _, tt := range tests {
		t.Run(string(tt.severity), func(t *testing.T) {
			level := exporter.severityToLevel(tt.severity)
			if level != tt.expected {
				t.Errorf("severityToLevel(%s) = %s, want %s", tt.severity, level, tt.expected)
			}
		})
	}
}

func TestSARIFExporter_EmptyReport(t *testing.T) {
	r := &report.Report{
		GeneratedAt: time.Now(),
		Source: report.Source{
			Type: "live",
			URL:  "test",
		},
		Findings: []*finding.Finding{},
	}

	exporter := NewSARIF()
	output, err := exporter.Export(r)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	var sarif sarifLog
	if err := json.Unmarshal(output, &sarif); err != nil {
		t.Fatalf("Output is not valid JSON: %v", err)
	}

	if len(sarif.Runs[0].Results) != 0 {
		t.Errorf("expected 0 results for empty report, got %d", len(sarif.Runs[0].Results))
	}
}
