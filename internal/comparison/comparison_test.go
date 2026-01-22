package comparison

import (
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

func TestCalculateMetricChange(t *testing.T) {
	tests := []struct {
		name           string
		metricName     string
		oldValue       float64
		newValue       float64
		higherIsBetter bool
		wantTrend      TrendDirection
		wantChange     float64
	}{
		{
			name:           "increase",
			metricName:     "health_score",
			oldValue:       70,
			newValue:       85,
			higherIsBetter: true,
			wantTrend:      TrendUp,
			wantChange:     15,
		},
		{
			name:           "decrease",
			metricName:     "health_score",
			oldValue:       85,
			newValue:       70,
			higherIsBetter: true,
			wantTrend:      TrendDown,
			wantChange:     -15,
		},
		{
			name:           "no change",
			metricName:     "health_score",
			oldValue:       75,
			newValue:       75,
			higherIsBetter: true,
			wantTrend:      TrendStable,
			wantChange:     0,
		},
		{
			name:           "issues decreased (good)",
			metricName:     "critical_issues",
			oldValue:       5,
			newValue:       2,
			higherIsBetter: false,
			wantTrend:      TrendDown,
			wantChange:     -3,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			change := CalculateMetricChange(tt.metricName, tt.oldValue, tt.newValue, tt.higherIsBetter)

			if change.Name != tt.metricName {
				t.Errorf("expected name %q, got %q", tt.metricName, change.Name)
			}
			if change.Change != tt.wantChange {
				t.Errorf("expected change %f, got %f", tt.wantChange, change.Change)
			}
			if change.Trend != tt.wantTrend {
				t.Errorf("expected trend %s, got %s", tt.wantTrend, change.Trend)
			}
		})
	}
}

func TestCalculateMetricChange_Percent(t *testing.T) {
	change := CalculateMetricChange("test", 100, 125, true)

	if change.ChangePercent == nil {
		t.Fatal("expected change percent to be set")
	}
	if *change.ChangePercent != 25.0 {
		t.Errorf("expected change percent 25.0, got %f", *change.ChangePercent)
	}
}

func TestCalculateMetricChange_ZeroOldValue(t *testing.T) {
	change := CalculateMetricChange("test", 0, 100, true)

	if change.ChangePercent != nil {
		t.Error("expected change percent to be nil when old value is 0")
	}
}

func TestFormatTimeDifference(t *testing.T) {
	now := time.Now()

	tests := []struct {
		name     string
		oldTime  time.Time
		newTime  time.Time
		expected string
	}{
		{
			name:     "days plural",
			oldTime:  now,
			newTime:  now.Add(72 * time.Hour),
			expected: "3 days",
		},
		{
			name:     "1 day",
			oldTime:  now,
			newTime:  now.Add(24 * time.Hour),
			expected: "1 day",
		},
		{
			name:     "hours plural",
			oldTime:  now,
			newTime:  now.Add(5 * time.Hour),
			expected: "5 hours",
		},
		{
			name:     "1 hour",
			oldTime:  now,
			newTime:  now.Add(1 * time.Hour),
			expected: "1 hour",
		},
		{
			name:     "minutes plural",
			oldTime:  now,
			newTime:  now.Add(30 * time.Minute),
			expected: "30 minutes",
		},
		{
			name:     "1 minute",
			oldTime:  now,
			newTime:  now.Add(1 * time.Minute),
			expected: "1 minute",
		},
		{
			name:     "less than a minute",
			oldTime:  now,
			newTime:  now.Add(30 * time.Second),
			expected: "less than a minute",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := formatTimeDifference(tt.oldTime, tt.newTime)
			if result != tt.expected {
				t.Errorf("expected %q, got %q", tt.expected, result)
			}
		})
	}
}

func TestCompareFindings(t *testing.T) {
	oldFindings := []*finding.Finding{
		finding.New("TEST-001", "Finding 1", "Desc", finding.SeverityWarning, finding.CategoryPerformance).WithIndex("idx1"),
		finding.New("TEST-002", "Finding 2", "Desc", finding.SeverityCritical, finding.CategorySchema).WithIndex("idx1"),
	}

	newFindings := []*finding.Finding{
		finding.New("TEST-001", "Finding 1", "Desc", finding.SeverityWarning, finding.CategoryPerformance).WithIndex("idx1"),
		finding.New("TEST-003", "Finding 3", "Desc", finding.SeverityInfo, finding.CategoryDocument).WithIndex("idx2"),
	}

	changes := compareFindings(oldFindings, newFindings)

	// Should have 2 changes: TEST-002 removed, TEST-003 added
	if len(changes) != 2 {
		t.Fatalf("expected 2 changes, got %d", len(changes))
	}

	var removed, added int
	for _, c := range changes {
		if c.ChangeType == ChangeRemoved {
			removed++
			if c.Finding.ID != "TEST-002" {
				t.Errorf("expected removed finding TEST-002, got %s", c.Finding.ID)
			}
		} else if c.ChangeType == ChangeAdded {
			added++
			if c.Finding.ID != "TEST-003" {
				t.Errorf("expected added finding TEST-003, got %s", c.Finding.ID)
			}
		}
	}

	if removed != 1 {
		t.Errorf("expected 1 removed, got %d", removed)
	}
	if added != 1 {
		t.Errorf("expected 1 added, got %d", added)
	}
}

func TestDetermineOverallTrend(t *testing.T) {
	tests := []struct {
		name           string
		healthTrend    TrendDirection
		criticalChange float64
		expected       TrendDirection
	}{
		{
			name:           "health up",
			healthTrend:    TrendUp,
			criticalChange: 0,
			expected:       TrendUp,
		},
		{
			name:           "health down",
			healthTrend:    TrendDown,
			criticalChange: 0,
			expected:       TrendDown,
		},
		{
			name:           "health stable, critical decreased",
			healthTrend:    TrendStable,
			criticalChange: -2,
			expected:       TrendUp,
		},
		{
			name:           "health stable, critical increased",
			healthTrend:    TrendStable,
			criticalChange: 2,
			expected:       TrendDown,
		},
		{
			name:           "everything stable",
			healthTrend:    TrendStable,
			criticalChange: 0,
			expected:       TrendStable,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			healthScore := MetricChange{Trend: tt.healthTrend}
			criticalIssues := MetricChange{Change: tt.criticalChange}
			warnings := MetricChange{}

			result := determineOverallTrend(healthScore, criticalIssues, warnings)
			if result != tt.expected {
				t.Errorf("expected %s, got %s", tt.expected, result)
			}
		})
	}
}

func TestIdentifyTrendAreas(t *testing.T) {
	pct := 10.0
	healthUp := MetricChange{Trend: TrendUp, ChangePercent: &pct}
	criticalDown := MetricChange{Change: -2}
	warningsDown := MetricChange{Change: -3}
	suggestions := MetricChange{}
	documents := MetricChange{}

	improvements, degradations := identifyTrendAreas(healthUp, criticalDown, warningsDown, suggestions, documents)

	if len(improvements) < 3 {
		t.Errorf("expected at least 3 improvements, got %d: %v", len(improvements), improvements)
	}
	if len(degradations) != 0 {
		t.Errorf("expected 0 degradations, got %d: %v", len(degradations), degradations)
	}
}

func TestGenerateRecommendations(t *testing.T) {
	changes := []FindingChange{
		{
			Finding:    finding.New("CRIT-1", "Critical", "Desc", finding.SeverityCritical, finding.CategoryPerformance),
			ChangeType: ChangeAdded,
		},
		{
			Finding:    finding.New("WARN-1", "Warning", "Desc", finding.SeverityWarning, finding.CategorySchema),
			ChangeType: ChangeAdded,
		},
	}

	recs := generateRecommendations(changes, TrendDown)

	if len(recs) < 2 {
		t.Errorf("expected at least 2 recommendations, got %d", len(recs))
	}

	// Should mention critical issues
	foundCritical := false
	for _, r := range recs {
		if contains(r, "critical") {
			foundCritical = true
			break
		}
	}
	if !foundCritical {
		t.Error("expected recommendation about critical issues")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestCompare(t *testing.T) {
	// Create mock collector data (minimal)
	oldReport := &report.Report{
		GeneratedAt: time.Now().Add(-24 * time.Hour),
		Version:     "1.0.0",
		Source: report.Source{
			Type: "live",
			URL:  "http://localhost:7700",
		},
		Instance: report.Instance{
			IndexCount:     2,
			TotalDocuments: 1000,
		},
		Summary: report.Summary{
			HealthScore:     70,
			CriticalCount:   2,
			WarningCount:    5,
			SuggestionCount: 3,
		},
		Findings: []*finding.Finding{
			finding.New("TEST-001", "Test", "Desc", finding.SeverityCritical, finding.CategoryPerformance).WithIndex("idx1"),
			finding.New("TEST-002", "Test", "Desc", finding.SeverityWarning, finding.CategorySchema).WithIndex("idx1"),
		},
	}

	newReport := &report.Report{
		GeneratedAt: time.Now(),
		Version:     "1.0.0",
		Source: report.Source{
			Type: "live",
			URL:  "http://localhost:7700",
		},
		Instance: report.Instance{
			IndexCount:     3,
			TotalDocuments: 1500,
		},
		Summary: report.Summary{
			HealthScore:     85,
			CriticalCount:   1,
			WarningCount:    3,
			SuggestionCount: 4,
		},
		Findings: []*finding.Finding{
			finding.New("TEST-002", "Test", "Desc", finding.SeverityWarning, finding.CategorySchema).WithIndex("idx1"),
			finding.New("TEST-003", "Test", "Desc", finding.SeverityInfo, finding.CategoryDocument).WithIndex("idx2"),
		},
	}

	compReport := Compare(oldReport, newReport)

	// Verify basic fields
	if compReport.Version != "1.0.0" {
		t.Errorf("expected version 1.0.0, got %s", compReport.Version)
	}

	// Health score should improve
	if compReport.Summary.HealthScore.Trend != TrendUp {
		t.Errorf("expected health score trend up, got %s", compReport.Summary.HealthScore.Trend)
	}
	if compReport.Summary.HealthScore.Change != 15 {
		t.Errorf("expected health score change 15, got %f", compReport.Summary.HealthScore.Change)
	}

	// Critical issues should decrease
	if compReport.Summary.CriticalIssues.Change != -1 {
		t.Errorf("expected critical issues change -1, got %f", compReport.Summary.CriticalIssues.Change)
	}

	// Overall trend should be up
	if compReport.Summary.OverallTrend != TrendUp {
		t.Errorf("expected overall trend up, got %s", compReport.Summary.OverallTrend)
	}

	// Should have finding changes
	if len(compReport.FindingChanges) != 2 {
		t.Errorf("expected 2 finding changes, got %d", len(compReport.FindingChanges))
	}

	// Test helper methods
	if compReport.NewFindingsCount() != 1 {
		t.Errorf("expected 1 new finding, got %d", compReport.NewFindingsCount())
	}
	if compReport.ResolvedFindingsCount() != 1 {
		t.Errorf("expected 1 resolved finding, got %d", compReport.ResolvedFindingsCount())
	}
}

func TestReportMethods(t *testing.T) {
	r := &Report{
		FindingChanges: []FindingChange{
			{ChangeType: ChangeAdded},
			{ChangeType: ChangeAdded},
			{ChangeType: ChangeRemoved},
		},
	}

	if r.NewFindingsCount() != 2 {
		t.Errorf("expected 2 new, got %d", r.NewFindingsCount())
	}
	if r.ResolvedFindingsCount() != 1 {
		t.Errorf("expected 1 resolved, got %d", r.ResolvedFindingsCount())
	}
}
