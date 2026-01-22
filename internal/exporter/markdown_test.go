package exporter

import (
	"strings"
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

func TestMarkdownExporter_Export(t *testing.T) {
	rpt := createTestReport()

	exp := NewMarkdown()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	result := string(output)

	// Check header
	if !strings.Contains(result, "# Meiliscan Analysis Report") {
		t.Error("Missing header")
	}

	// Check instance info section
	if !strings.Contains(result, "## Instance Information") {
		t.Error("Missing instance info section")
	}
	if !strings.Contains(result, "**Version**: 1.16.0") {
		t.Error("Missing version info")
	}
	if !strings.Contains(result, "**Indexes**: 2") {
		t.Error("Missing index count")
	}
	if !strings.Contains(result, "**Total Documents**: 5000") {
		t.Error("Missing document count")
	}

	// Check summary section
	if !strings.Contains(result, "## Summary") {
		t.Error("Missing summary section")
	}
	if !strings.Contains(result, "**Health Score**: 65/100") {
		t.Error("Missing health score")
	}
	if !strings.Contains(result, "| Critical | 1 |") {
		t.Error("Missing critical count in table")
	}
	if !strings.Contains(result, "| Warning | 1 |") {
		t.Error("Missing warning count in table")
	}

	// Check findings section
	if !strings.Contains(result, "## Findings") {
		t.Error("Missing findings section")
	}
	if !strings.Contains(result, "MEILI-S001") {
		t.Error("Missing first finding ID")
	}
	if !strings.Contains(result, "Wildcard searchable attributes") {
		t.Error("Missing first finding title")
	}
	if !strings.Contains(result, "**Index**: `products`") {
		t.Error("Missing index reference")
	}

	// Check footer
	if !strings.Contains(result, "Generated at") {
		t.Error("Missing footer")
	}
	if !strings.Contains(result, "by Meiliscan") {
		t.Error("Missing branding in footer")
	}
}

func TestMarkdownExporter_NoFindings(t *testing.T) {
	rpt := &report.Report{
		GeneratedAt: time.Now(),
		Version:     "1.0.0",
		Source:      report.Source{Type: "live"},
		Instance: report.Instance{
			Version:    "1.16.0",
			IndexCount: 1,
		},
		Summary:  report.Summary{HealthScore: 100, HealthStatus: "healthy"},
		Findings: nil,
	}

	exp := NewMarkdown()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	result := string(output)

	// Should show "no issues found" message
	if !strings.Contains(result, "No issues found") {
		t.Error("Should show 'no issues found' message")
	}
}

func TestMarkdownExporter_FindingWithFixCommand(t *testing.T) {
	rpt := &report.Report{
		GeneratedAt: time.Now(),
		Version:     "1.0.0",
		Source:      report.Source{Type: "live", URL: "http://localhost:7700"},
		Instance:    report.Instance{Version: "1.16.0"},
		Summary:     report.Summary{HealthScore: 75, CriticalCount: 1, TotalFindings: 1},
		Findings: []*finding.Finding{
			{
				ID:             "MEILI-S001",
				Title:          "Test Finding",
				Description:    "Test description",
				Severity:       finding.SeverityCritical,
				Category:       finding.CategorySchema,
				IndexUID:       "products",
				Recommendation: "Fix the issue",
				FixCommand:     "curl -X PATCH ...",
			},
		},
	}

	exp := NewMarkdown()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	result := string(output)

	// Check recommendation
	if !strings.Contains(result, "**Recommendation**: Fix the issue") {
		t.Error("Missing recommendation")
	}

	// Check fix command with code block
	if !strings.Contains(result, "**Fix Command**:") {
		t.Error("Missing fix command label")
	}
	if !strings.Contains(result, "```bash") {
		t.Error("Missing bash code block")
	}
	if !strings.Contains(result, "curl -X PATCH ...") {
		t.Error("Missing fix command content")
	}
}

func TestMarkdownExporter_AllSeverities(t *testing.T) {
	rpt := &report.Report{
		GeneratedAt: time.Now(),
		Version:     "1.0.0",
		Source:      report.Source{Type: "live"},
		Instance:    report.Instance{},
		Summary: report.Summary{
			CriticalCount:   1,
			WarningCount:    1,
			SuggestionCount: 1,
			InfoCount:       1,
			TotalFindings:   4,
		},
		Findings: []*finding.Finding{
			{ID: "C1", Title: "Critical", Severity: finding.SeverityCritical, Category: finding.CategorySchema},
			{ID: "W1", Title: "Warning", Severity: finding.SeverityWarning, Category: finding.CategorySchema},
			{ID: "S1", Title: "Suggestion", Severity: finding.SeveritySuggestion, Category: finding.CategorySchema},
			{ID: "I1", Title: "Info", Severity: finding.SeverityInfo, Category: finding.CategorySchema},
		},
	}

	exp := NewMarkdown()
	output, err := exp.Export(rpt)
	if err != nil {
		t.Fatalf("Export failed: %v", err)
	}

	result := string(output)

	// Check all severity icons are present
	if !strings.Contains(result, "[CRITICAL]") {
		t.Error("Missing CRITICAL icon")
	}
	if !strings.Contains(result, "[WARNING]") {
		t.Error("Missing WARNING icon")
	}
	if !strings.Contains(result, "[SUGGESTION]") {
		t.Error("Missing SUGGESTION icon")
	}
	if !strings.Contains(result, "[INFO]") {
		t.Error("Missing INFO icon")
	}
}

func TestSeverityIcon(t *testing.T) {
	tests := []struct {
		severity finding.Severity
		expected string
	}{
		{finding.SeverityCritical, "[CRITICAL]"},
		{finding.SeverityWarning, "[WARNING]"},
		{finding.SeveritySuggestion, "[SUGGESTION]"},
		{finding.SeverityInfo, "[INFO]"},
		{finding.Severity("unknown"), ""},
	}

	for _, tt := range tests {
		t.Run(string(tt.severity), func(t *testing.T) {
			result := severityIcon(tt.severity)
			if result != tt.expected {
				t.Errorf("severityIcon(%q) = %q, want %q", tt.severity, result, tt.expected)
			}
		})
	}
}

func TestFormatBytes(t *testing.T) {
	tests := []struct {
		input    int64
		expected string
	}{
		{0, "0 B"},
		{500, "500 B"},
		{1023, "1023 B"},
		{1024, "1.0 KB"},
		{1536, "1.5 KB"},
		{1048576, "1.0 MB"},
		{1073741824, "1.0 GB"},
		{1099511627776, "1.0 TB"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			result := formatBytes(tt.input)
			if result != tt.expected {
				t.Errorf("formatBytes(%d) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}
