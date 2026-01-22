// Package comparison provides report comparison and trend analysis.
package comparison

import (
	"fmt"
	"math"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

// TrendDirection indicates the direction of a metric trend.
type TrendDirection string

const (
	TrendUp     TrendDirection = "up"
	TrendDown   TrendDirection = "down"
	TrendStable TrendDirection = "stable"
)

// ChangeType represents the type of change detected.
type ChangeType string

const (
	ChangeAdded     ChangeType = "added"
	ChangeRemoved   ChangeType = "removed"
	ChangeImproved  ChangeType = "improved"
	ChangeDegraded  ChangeType = "degraded"
	ChangeUnchanged ChangeType = "unchanged"
)

// MetricChange represents a change in a numeric metric.
type MetricChange struct {
	Name          string         `json:"name"`
	OldValue      *float64       `json:"old_value,omitempty"`
	NewValue      *float64       `json:"new_value,omitempty"`
	Change        float64        `json:"change"`
	ChangePercent *float64       `json:"change_percent,omitempty"`
	Trend         TrendDirection `json:"trend"`
}

// CalculateMetricChange calculates the change between two values.
func CalculateMetricChange(name string, oldValue, newValue float64, higherIsBetter bool) MetricChange {
	change := newValue - oldValue

	var changePercent *float64
	if oldValue != 0 {
		pct := (change / oldValue) * 100
		changePercent = &pct
	}

	var trend TrendDirection
	if change > 0 {
		trend = TrendUp
	} else if change < 0 {
		trend = TrendDown
	} else {
		trend = TrendStable
	}

	return MetricChange{
		Name:          name,
		OldValue:      &oldValue,
		NewValue:      &newValue,
		Change:        change,
		ChangePercent: changePercent,
		Trend:         trend,
	}
}

// FindingChange represents a change in a finding between reports.
type FindingChange struct {
	Finding    *finding.Finding `json:"finding"`
	ChangeType ChangeType       `json:"change_type"`
}

// IndexChange represents changes for a specific index.
type IndexChange struct {
	UID              string                 `json:"uid"`
	ChangeType       ChangeType             `json:"change_type"`
	DocumentCount    *MetricChange          `json:"document_count,omitempty"`
	FindingCount     *MetricChange          `json:"finding_count,omitempty"`
	NewFindings      []*finding.Finding     `json:"new_findings,omitempty"`
	ResolvedFindings []*finding.Finding     `json:"resolved_findings,omitempty"`
	SettingsChanged  bool                   `json:"settings_changed"`
	SettingsDiff     map[string]SettingDiff `json:"settings_diff,omitempty"`
}

// SettingDiff represents a change in a setting value.
type SettingDiff struct {
	Old interface{} `json:"old"`
	New interface{} `json:"new"`
}

// Summary contains the comparison summary.
type Summary struct {
	OldReportDate time.Time `json:"old_report_date"`
	NewReportDate time.Time `json:"new_report_date"`
	TimeBetween   string    `json:"time_between"`

	// Index changes
	IndexesAdded   []string `json:"indexes_added"`
	IndexesRemoved []string `json:"indexes_removed"`
	IndexesChanged []string `json:"indexes_changed"`

	// Metric changes
	HealthScore    MetricChange `json:"health_score"`
	TotalDocuments MetricChange `json:"total_documents"`
	TotalIndexes   MetricChange `json:"total_indexes"`
	CriticalIssues MetricChange `json:"critical_issues"`
	Warnings       MetricChange `json:"warnings"`
	Suggestions    MetricChange `json:"suggestions"`

	// Overall assessment
	OverallTrend     TrendDirection `json:"overall_trend"`
	ImprovementAreas []string       `json:"improvement_areas"`
	DegradationAreas []string       `json:"degradation_areas"`
}

// Report represents a complete comparison between two analysis reports.
type Report struct {
	Version     string    `json:"version"`
	GeneratedAt time.Time `json:"generated_at"`

	// Source reports
	OldSource SourceInfo `json:"old_source"`
	NewSource SourceInfo `json:"new_source"`

	// Summary
	Summary Summary `json:"summary"`

	// Detailed changes
	IndexChanges   map[string]*IndexChange `json:"index_changes"`
	FindingChanges []FindingChange         `json:"finding_changes"`

	// Recommendations
	Recommendations []string `json:"recommendations"`
}

// SourceInfo contains source report information.
type SourceInfo struct {
	Type string `json:"type"`
	URL  string `json:"url,omitempty"`
	Path string `json:"path,omitempty"`
}

// Compare compares two analysis reports and generates a comparison report.
func Compare(oldReport, newReport *report.Report) *Report {
	compReport := &Report{
		Version:     "1.0.0",
		GeneratedAt: time.Now(),
		OldSource: SourceInfo{
			Type: oldReport.Source.Type,
			URL:  oldReport.Source.URL,
			Path: oldReport.Source.Path,
		},
		NewSource: SourceInfo{
			Type: newReport.Source.Type,
			URL:  newReport.Source.URL,
			Path: newReport.Source.Path,
		},
		IndexChanges: make(map[string]*IndexChange),
	}

	// Calculate time between reports
	timeBetween := formatTimeDifference(oldReport.GeneratedAt, newReport.GeneratedAt)

	// Detect index changes (comparing by index count since we don't have full index list in report)
	compReport.Summary = Summary{
		OldReportDate: oldReport.GeneratedAt,
		NewReportDate: newReport.GeneratedAt,
		TimeBetween:   timeBetween,
	}

	// Calculate metric changes
	compReport.Summary.HealthScore = CalculateMetricChange(
		"health_score",
		float64(oldReport.Summary.HealthScore),
		float64(newReport.Summary.HealthScore),
		true,
	)

	compReport.Summary.TotalDocuments = CalculateMetricChange(
		"total_documents",
		float64(oldReport.Instance.TotalDocuments),
		float64(newReport.Instance.TotalDocuments),
		true,
	)

	compReport.Summary.TotalIndexes = CalculateMetricChange(
		"total_indexes",
		float64(oldReport.Instance.IndexCount),
		float64(newReport.Instance.IndexCount),
		true,
	)

	compReport.Summary.CriticalIssues = CalculateMetricChange(
		"critical_issues",
		float64(oldReport.Summary.CriticalCount),
		float64(newReport.Summary.CriticalCount),
		false, // Lower is better
	)

	compReport.Summary.Warnings = CalculateMetricChange(
		"warnings",
		float64(oldReport.Summary.WarningCount),
		float64(newReport.Summary.WarningCount),
		false, // Lower is better
	)

	compReport.Summary.Suggestions = CalculateMetricChange(
		"suggestions",
		float64(oldReport.Summary.SuggestionCount),
		float64(newReport.Summary.SuggestionCount),
		false, // Lower is better
	)

	// Compare findings
	compReport.FindingChanges = compareFindings(oldReport.Findings, newReport.Findings)

	// Determine overall trend
	compReport.Summary.OverallTrend = determineOverallTrend(
		compReport.Summary.HealthScore,
		compReport.Summary.CriticalIssues,
		compReport.Summary.Warnings,
	)

	// Identify improvement and degradation areas
	compReport.Summary.ImprovementAreas, compReport.Summary.DegradationAreas = identifyTrendAreas(
		compReport.Summary.HealthScore,
		compReport.Summary.CriticalIssues,
		compReport.Summary.Warnings,
		compReport.Summary.Suggestions,
		compReport.Summary.TotalDocuments,
	)

	// Generate recommendations
	compReport.Recommendations = generateRecommendations(
		compReport.FindingChanges,
		compReport.Summary.OverallTrend,
	)

	return compReport
}

func formatTimeDifference(oldTime, newTime time.Time) string {
	diff := newTime.Sub(oldTime)
	days := int(diff.Hours() / 24)
	hours := int(diff.Hours()) % 24
	minutes := int(diff.Minutes()) % 60

	if days > 0 {
		if days == 1 {
			return "1 day"
		}
		return fmt.Sprintf("%d days", days)
	} else if hours > 0 {
		if hours == 1 {
			return "1 hour"
		}
		return fmt.Sprintf("%d hours", hours)
	} else if minutes > 0 {
		if minutes == 1 {
			return "1 minute"
		}
		return fmt.Sprintf("%d minutes", minutes)
	}
	return "less than a minute"
}

func compareFindings(oldFindings, newFindings []*finding.Finding) []FindingChange {
	var changes []FindingChange

	// Create maps for lookup
	oldMap := make(map[string]*finding.Finding)
	for _, f := range oldFindings {
		key := findingKey(f)
		oldMap[key] = f
	}

	newMap := make(map[string]*finding.Finding)
	for _, f := range newFindings {
		key := findingKey(f)
		newMap[key] = f
	}

	// Find resolved (removed) findings
	for key, f := range oldMap {
		if _, exists := newMap[key]; !exists {
			changes = append(changes, FindingChange{
				Finding:    f,
				ChangeType: ChangeRemoved,
			})
		}
	}

	// Find new (added) findings
	for key, f := range newMap {
		if _, exists := oldMap[key]; !exists {
			changes = append(changes, FindingChange{
				Finding:    f,
				ChangeType: ChangeAdded,
			})
		}
	}

	return changes
}

// findingKey creates a unique key for a finding.
// Uses ID + IndexUID to uniquely identify a finding instance.
func findingKey(f *finding.Finding) string {
	return f.ID + ":" + f.IndexUID
}

func determineOverallTrend(healthScore, criticalIssues, warnings MetricChange) TrendDirection {
	// Health score is the primary indicator
	if healthScore.Trend == TrendUp {
		return TrendUp
	} else if healthScore.Trend == TrendDown {
		return TrendDown
	}

	// If health score is stable, check issues (for issues, down is good)
	if criticalIssues.Change < 0 {
		return TrendUp
	} else if criticalIssues.Change > 0 {
		return TrendDown
	}

	return TrendStable
}

func identifyTrendAreas(healthScore, criticalIssues, warnings, suggestions, totalDocuments MetricChange) ([]string, []string) {
	var improvements, degradations []string

	// Health score
	if healthScore.Trend == TrendUp {
		if healthScore.ChangePercent != nil {
			improvements = append(improvements, fmt.Sprintf("Health score improved by %.1f%%", *healthScore.ChangePercent))
		} else {
			improvements = append(improvements, "Health score improved")
		}
	} else if healthScore.Trend == TrendDown {
		if healthScore.ChangePercent != nil {
			degradations = append(degradations, fmt.Sprintf("Health score decreased by %.1f%%", math.Abs(*healthScore.ChangePercent)))
		} else {
			degradations = append(degradations, "Health score decreased")
		}
	}

	// Critical issues (lower is better)
	if criticalIssues.Change < 0 {
		improvements = append(improvements, fmt.Sprintf("Resolved %d critical issue(s)", int(math.Abs(criticalIssues.Change))))
	} else if criticalIssues.Change > 0 {
		degradations = append(degradations, fmt.Sprintf("Added %d new critical issue(s)", int(criticalIssues.Change)))
	}

	// Warnings (lower is better)
	if warnings.Change < 0 {
		improvements = append(improvements, fmt.Sprintf("Resolved %d warning(s)", int(math.Abs(warnings.Change))))
	} else if warnings.Change > 0 {
		degradations = append(degradations, fmt.Sprintf("Added %d new warning(s)", int(warnings.Change)))
	}

	// Document growth
	if totalDocuments.Trend == TrendUp && totalDocuments.Change > 0 {
		if totalDocuments.ChangePercent != nil && *totalDocuments.ChangePercent > 10 {
			improvements = append(improvements, fmt.Sprintf("Document count grew by %.1f%%", *totalDocuments.ChangePercent))
		}
	}

	return improvements, degradations
}

func generateRecommendations(findingChanges []FindingChange, overallTrend TrendDirection) []string {
	var recommendations []string

	// Count new critical issues
	newCritical := 0
	for _, fc := range findingChanges {
		if fc.ChangeType == ChangeAdded && fc.Finding.Severity == finding.SeverityCritical {
			newCritical++
		}
	}
	if newCritical > 0 {
		recommendations = append(recommendations, fmt.Sprintf("Address %d new critical issue(s) as soon as possible", newCritical))
	}

	// Overall trend-based recommendations
	if overallTrend == TrendUp {
		recommendations = append(recommendations, "Good progress! Continue monitoring and addressing remaining suggestions")
	} else if overallTrend == TrendDown {
		recommendations = append(recommendations, "Configuration health has degraded - prioritize fixing critical issues")
	}

	return recommendations
}

// NewFindingsCount returns the count of new findings from the comparison.
func (r *Report) NewFindingsCount() int {
	count := 0
	for _, fc := range r.FindingChanges {
		if fc.ChangeType == ChangeAdded {
			count++
		}
	}
	return count
}

// ResolvedFindingsCount returns the count of resolved findings from the comparison.
func (r *Report) ResolvedFindingsCount() int {
	count := 0
	for _, fc := range r.FindingChanges {
		if fc.ChangeType == ChangeRemoved {
			count++
		}
	}
	return count
}
