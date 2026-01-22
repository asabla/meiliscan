package exporter

import (
	"strings"
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

func TestAgentExporter_Export(t *testing.T) {
	// Create a sample report
	rpt := &report.Report{
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
			DatabaseSize:   524288000, // 500MB
		},
		Summary: report.Summary{
			HealthScore:     65,
			HealthStatus:    "warning",
			TotalFindings:   4,
			CriticalCount:   1,
			WarningCount:    1,
			SuggestionCount: 1,
			InfoCount:       1,
		},
		Findings: []*finding.Finding{
			{
				ID:             "MEILI-S001",
				Title:          "Wildcard searchable attributes",
				Description:    "All fields are searchable by default, which impacts search performance.",
				Severity:       finding.SeverityCritical,
				Category:       finding.CategorySchema,
				IndexUID:       "products",
				Recommendation: "Specify explicit searchable attributes.",
				FixCommand:     "curl -X PATCH 'http://localhost:7700/indexes/products/settings' -H 'Content-Type: application/json' --data-binary '{\"searchableAttributes\":[\"title\",\"description\"]}'",
			},
			{
				ID:             "MEILI-B001",
				Title:          "Settings updated after documents",
				Description:    "Settings were updated after documents were added.",
				Severity:       finding.SeverityWarning,
				Category:       finding.CategoryBestPractice,
				IndexUID:       "products",
				Recommendation: "Configure settings before adding documents.",
			},
			{
				ID:          "MEILI-S006",
				Title:       "No stop words configured",
				Description: "No stop words are configured for this index.",
				Severity:    finding.SeveritySuggestion,
				Category:    finding.CategorySchema,
				IndexUID:    "articles",
			},
			{
				ID:          "MEILI-S007",
				Title:       "Default ranking rules",
				Description: "Using default ranking rules.",
				Severity:    finding.SeverityInfo,
				Category:    finding.CategorySchema,
				IndexUID:    "articles",
			},
		},
	}

	t.Run("default settings includes all findings", func(t *testing.T) {
		exp := NewAgent()
		output, err := exp.Export(rpt)
		if err != nil {
			t.Fatalf("Export failed: %v", err)
		}

		result := string(output)

		// Check header
		if !strings.Contains(result, "# MeiliSearch Analysis Context") {
			t.Error("Missing header")
		}

		// Check summary section
		if !strings.Contains(result, "## Current State Summary") {
			t.Error("Missing summary section")
		}
		if !strings.Contains(result, "65/100") {
			t.Error("Missing health score")
		}
		if !strings.Contains(result, "needs attention") {
			t.Error("Missing health description")
		}

		// Check all severity sections
		if !strings.Contains(result, "## Critical Issues (Fix First)") {
			t.Error("Missing critical section")
		}
		if !strings.Contains(result, "## Warnings (Should Address)") {
			t.Error("Missing warnings section")
		}
		if !strings.Contains(result, "## Suggestions (Consider When Convenient)") {
			t.Error("Missing suggestions section")
		}
		if !strings.Contains(result, "## Informational Notes") {
			t.Error("Missing info section")
		}

		// Check fix script
		if !strings.Contains(result, "## Quick Fix Script") {
			t.Error("Missing quick fix script")
		}
		if !strings.Contains(result, "MEILISEARCH_URL=") {
			t.Error("Missing URL variable in fix script")
		}

		// Check index overview
		if !strings.Contains(result, "## Index Overview") {
			t.Error("Missing index overview")
		}
		if !strings.Contains(result, "| `products` |") {
			t.Error("Missing products index in overview")
		}
	})

	t.Run("IncludeAllFindings=false excludes suggestions and info", func(t *testing.T) {
		exp := NewAgentWithOptions(false, 0)
		output, err := exp.Export(rpt)
		if err != nil {
			t.Fatalf("Export failed: %v", err)
		}

		result := string(output)

		// Should have critical and warning
		if !strings.Contains(result, "## Critical Issues") {
			t.Error("Should have critical section")
		}
		if !strings.Contains(result, "## Warnings") {
			t.Error("Should have warnings section")
		}

		// Should NOT have suggestions and info
		if strings.Contains(result, "## Suggestions") {
			t.Error("Should not have suggestions section")
		}
		if strings.Contains(result, "## Informational Notes") {
			t.Error("Should not have info section")
		}

		// Should show filtered count
		if !strings.Contains(result, "Showing:** 2 of 4 findings") {
			t.Error("Should indicate filtered findings")
		}
	})

	t.Run("MaxFindings limits output", func(t *testing.T) {
		exp := NewAgentWithOptions(true, 2)
		output, err := exp.Export(rpt)
		if err != nil {
			t.Fatalf("Export failed: %v", err)
		}

		result := string(output)

		// Should show limited count
		if !strings.Contains(result, "Showing:** 2 of 4 findings") {
			t.Error("Should indicate limited findings")
		}

		// Count finding headers (### MEILI-)
		count := strings.Count(result, "### MEILI-")
		if count != 2 {
			t.Errorf("Expected 2 findings, got %d", count)
		}
	})

	t.Run("no findings produces minimal output", func(t *testing.T) {
		emptyReport := &report.Report{
			GeneratedAt: time.Now(),
			Source:      report.Source{Type: "live", URL: "http://localhost:7700"},
			Instance:    report.Instance{Version: "1.16.0", IndexCount: 1},
			Summary:     report.Summary{HealthScore: 100, HealthStatus: "healthy"},
			Findings:    nil,
		}

		exp := NewAgent()
		output, err := exp.Export(emptyReport)
		if err != nil {
			t.Fatalf("Export failed: %v", err)
		}

		result := string(output)

		// Should have header and summary
		if !strings.Contains(result, "# MeiliSearch Analysis Context") {
			t.Error("Missing header")
		}
		if !strings.Contains(result, "100/100") {
			t.Error("Missing health score")
		}

		// Should NOT have finding sections
		if strings.Contains(result, "## Critical Issues") {
			t.Error("Should not have critical section when no findings")
		}
		if strings.Contains(result, "## Quick Fix Script") {
			t.Error("Should not have fix script when no findings with fixes")
		}
	})
}

func TestDescribeHealthScore(t *testing.T) {
	tests := []struct {
		score    int
		expected string
	}{
		{100, "excellent"},
		{95, "excellent"},
		{90, "excellent"},
		{89, "good"},
		{70, "good"},
		{69, "needs attention"},
		{50, "needs attention"},
		{49, "poor"},
		{30, "poor"},
		{29, "critical"},
		{0, "critical"},
	}

	for _, tt := range tests {
		t.Run(string(rune(tt.score)), func(t *testing.T) {
			result := describeHealthScore(tt.score)
			if result != tt.expected {
				t.Errorf("describeHealthScore(%d) = %q, want %q", tt.score, result, tt.expected)
			}
		})
	}
}

func TestFormatNumber(t *testing.T) {
	tests := []struct {
		input    int64
		expected string
	}{
		{0, "0"},
		{999, "999"},
		{1000, "1.0K"},
		{1500, "1.5K"},
		{999999, "1000.0K"},
		{1000000, "1.0M"},
		{1500000, "1.5M"},
		{10000000, "10.0M"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			result := formatNumber(tt.input)
			if result != tt.expected {
				t.Errorf("formatNumber(%d) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestTruncate(t *testing.T) {
	tests := []struct {
		input    string
		maxLen   int
		expected string
	}{
		{"short", 10, "short"},
		{"exactly10!", 10, "exactly10!"},
		{"this is a longer string", 10, "this is..."},
		{"", 5, ""},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := truncate(tt.input, tt.maxLen)
			if result != tt.expected {
				t.Errorf("truncate(%q, %d) = %q, want %q", tt.input, tt.maxLen, result, tt.expected)
			}
		})
	}
}

func TestGroupBySeverity(t *testing.T) {
	findings := []*finding.Finding{
		{ID: "1", Severity: finding.SeverityCritical},
		{ID: "2", Severity: finding.SeverityWarning},
		{ID: "3", Severity: finding.SeverityCritical},
		{ID: "4", Severity: finding.SeveritySuggestion},
		{ID: "5", Severity: finding.SeverityInfo},
		{ID: "6", Severity: finding.SeverityWarning},
	}

	criticals, warnings, suggestions, infos := groupBySeverity(findings)

	if len(criticals) != 2 {
		t.Errorf("Expected 2 criticals, got %d", len(criticals))
	}
	if len(warnings) != 2 {
		t.Errorf("Expected 2 warnings, got %d", len(warnings))
	}
	if len(suggestions) != 1 {
		t.Errorf("Expected 1 suggestion, got %d", len(suggestions))
	}
	if len(infos) != 1 {
		t.Errorf("Expected 1 info, got %d", len(infos))
	}
}
