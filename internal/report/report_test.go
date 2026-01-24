package report

import (
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

func TestHealthScoreCalculation(t *testing.T) {
	tests := []struct {
		name           string
		findings       []*finding.Finding
		expectedScore  int
		expectedStatus string
	}{
		{
			name:           "no findings = perfect health",
			findings:       []*finding.Finding{},
			expectedScore:  100,
			expectedStatus: "healthy",
		},
		{
			name: "one critical drops score by 25",
			findings: []*finding.Finding{
				finding.New("TEST-001", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
			},
			expectedScore:  75,
			expectedStatus: "critical",
		},
		{
			name: "one warning drops score by 10",
			findings: []*finding.Finding{
				finding.New("TEST-001", "Test", "Test", finding.SeverityWarning, finding.CategorySchema),
			},
			expectedScore:  90,
			expectedStatus: "warning",
		},
		{
			name: "one suggestion drops score by 3",
			findings: []*finding.Finding{
				finding.New("TEST-001", "Test", "Test", finding.SeveritySuggestion, finding.CategorySchema),
			},
			expectedScore:  97,
			expectedStatus: "healthy",
		},
		{
			name: "info drops score by 1",
			findings: []*finding.Finding{
				finding.New("TEST-001", "Test", "Test", finding.SeverityInfo, finding.CategorySchema),
			},
			expectedScore:  99,
			expectedStatus: "healthy",
		},
		{
			name: "multiple findings compound",
			findings: []*finding.Finding{
				finding.New("TEST-001", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
				finding.New("TEST-002", "Test", "Test", finding.SeverityWarning, finding.CategorySchema),
				finding.New("TEST-003", "Test", "Test", finding.SeveritySuggestion, finding.CategorySchema),
			},
			expectedScore:  62, // 100 - 25 - 10 - 3
			expectedStatus: "critical",
		},
		{
			name: "score floors at 0",
			findings: []*finding.Finding{
				finding.New("TEST-001", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
				finding.New("TEST-002", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
				finding.New("TEST-003", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
				finding.New("TEST-004", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
				finding.New("TEST-005", "Test", "Test", finding.SeverityCritical, finding.CategorySchema),
			},
			expectedScore:  0, // Would be -25 but floors at 0
			expectedStatus: "critical",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				SourceType: "test",
			}

			report := New(data, tt.findings)

			if report.Summary.HealthScore != tt.expectedScore {
				t.Errorf("expected health score %d, got %d", tt.expectedScore, report.Summary.HealthScore)
			}

			if report.Summary.HealthStatus != tt.expectedStatus {
				t.Errorf("expected status %s, got %s", tt.expectedStatus, report.Summary.HealthStatus)
			}
		})
	}
}

func TestFindingsSorting(t *testing.T) {
	findings := []*finding.Finding{
		finding.New("TEST-003", "Info", "Test", finding.SeverityInfo, finding.CategorySchema).WithIndex("b-index"),
		finding.New("TEST-001", "Critical", "Test", finding.SeverityCritical, finding.CategorySchema).WithIndex("a-index"),
		finding.New("TEST-002", "Warning", "Test", finding.SeverityWarning, finding.CategorySchema).WithIndex("a-index"),
	}

	data := &collector.CollectedData{SourceType: "test"}
	report := New(data, findings)

	// Should be sorted: Critical first, then by index, then by ID
	if report.Findings[0].ID != "TEST-001" {
		t.Errorf("expected first finding to be TEST-001 (critical), got %s", report.Findings[0].ID)
	}
	if report.Findings[1].ID != "TEST-002" {
		t.Errorf("expected second finding to be TEST-002 (warning), got %s", report.Findings[1].ID)
	}
	if report.Findings[2].ID != "TEST-003" {
		t.Errorf("expected third finding to be TEST-003 (info), got %s", report.Findings[2].ID)
	}
}
