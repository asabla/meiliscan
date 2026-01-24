package exporter

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

func TestJSONExporter_Export(t *testing.T) {
	rpt := createTestReport()

	exp := NewJSON()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	// Verify it's valid JSON
	var parsed map[string]interface{}
	if err := json.Unmarshal(output, &parsed); err != nil {
		t.Fatalf("Output is not valid JSON: %v", err)
	}

	// Check required fields exist
	requiredFields := []string{"generated_at", "version", "source", "instance", "findings", "summary"}
	for _, field := range requiredFields {
		if _, ok := parsed[field]; !ok {
			t.Errorf("Missing required field: %s", field)
		}
	}

	// Check summary values
	summary, ok := parsed["summary"].(map[string]interface{})
	if !ok {
		t.Fatal("Summary is not an object")
	}
	if summary["health_score"].(float64) != 65 {
		t.Errorf("health_score = %v, want 65", summary["health_score"])
	}
	if summary["critical_count"].(float64) != 1 {
		t.Errorf("critical_count = %v, want 1", summary["critical_count"])
	}

	// Check findings count
	findings, ok := parsed["findings"].([]interface{})
	if !ok {
		t.Fatal("Findings is not an array")
	}
	if len(findings) != 2 {
		t.Errorf("len(findings) = %d, want 2", len(findings))
	}
}

func TestJSONExporter_EmptyReport(t *testing.T) {
	rpt := &report.Report{
		GeneratedAt: time.Now(),
		Version:     "1.0.0",
		Source:      report.Source{Type: "live"},
		Instance:    report.Instance{},
		Findings:    nil,
		Summary:     report.Summary{HealthScore: 100},
	}

	exp := NewJSON()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	var parsed map[string]interface{}
	if err := json.Unmarshal(output, &parsed); err != nil {
		t.Fatalf("Output is not valid JSON: %v", err)
	}

	// Findings should be null or empty array
	findings := parsed["findings"]
	if findings != nil {
		if arr, ok := findings.([]interface{}); ok && len(arr) > 0 {
			t.Error("Expected nil or empty findings array")
		}
	}
}

func TestJSONExporter_Indentation(t *testing.T) {
	rpt := createTestReport()

	exp := NewJSON()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	// Default should be indented (contains newlines)
	if !containsNewline(output) {
		t.Error("Expected indented JSON with newlines")
	}
}

func containsNewline(b []byte) bool {
	for _, c := range b {
		if c == '\n' {
			return true
		}
	}
	return false
}

func createTestReport() *report.Report {
	return &report.Report{
		GeneratedAt: time.Date(2026, 1, 22, 10, 0, 0, 0, time.UTC),
		Version:     "1.0.0",
		Source: report.Source{
			Type: "live",
			URL:  "http://localhost:7700",
		},
		Instance: report.Instance{
			Version:        "1.16.0",
			IndexCount:     2,
			TotalDocuments: 5000,
			DatabaseSize:   524288000,
		},
		Summary: report.Summary{
			HealthScore:     65,
			HealthStatus:    "warning",
			TotalFindings:   2,
			CriticalCount:   1,
			WarningCount:    1,
			SuggestionCount: 0,
			InfoCount:       0,
		},
		Findings: []*finding.Finding{
			{
				ID:          "MEILI-S001",
				Title:       "Wildcard searchable attributes",
				Description: "All fields are searchable by default.",
				Severity:    finding.SeverityCritical,
				Category:    finding.CategorySchema,
				IndexUID:    "products",
			},
			{
				ID:          "MEILI-B001",
				Title:       "Settings updated after documents",
				Description: "Settings were updated after documents were added.",
				Severity:    finding.SeverityWarning,
				Category:    finding.CategoryBestPractice,
				IndexUID:    "products",
			},
		},
	}
}
