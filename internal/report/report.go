// Package report provides the report model and health scoring.
package report

import (
	"sort"
	"time"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// Report represents the complete analysis report.
type Report struct {
	// Metadata
	GeneratedAt time.Time `json:"generated_at"`
	Version     string    `json:"version"`

	// Source information
	Source Source `json:"source"`

	// Instance information
	Instance Instance `json:"instance"`

	// Findings
	Findings []*finding.Finding `json:"findings"`

	// Summary
	Summary Summary `json:"summary"`
}

// Source describes the analyzed source.
type Source struct {
	Type string `json:"type"` // "live" or "dump"
	URL  string `json:"url,omitempty"`
	Path string `json:"path,omitempty"`
}

// Instance contains instance-level information.
type Instance struct {
	Version        string `json:"version"`
	IndexCount     int    `json:"index_count"`
	TotalDocuments int64  `json:"total_documents"`
	DatabaseSize   int64  `json:"database_size"`
}

// Summary contains aggregated statistics.
type Summary struct {
	HealthScore     int    `json:"health_score"`
	HealthStatus    string `json:"health_status"` // "healthy", "warning", "critical"
	TotalFindings   int    `json:"total_findings"`
	CriticalCount   int    `json:"critical_count"`
	WarningCount    int    `json:"warning_count"`
	SuggestionCount int    `json:"suggestion_count"`
	InfoCount       int    `json:"info_count"`
}

// New creates a new Report from collected data and findings.
func New(data *collector.CollectedData, findings []*finding.Finding) *Report {
	r := &Report{
		GeneratedAt: time.Now(),
		Version:     "1.0.0", // TODO: inject from build
		Findings:    findings,
	}

	// Set source info
	r.Source = Source{
		Type: data.SourceType,
		URL:  data.SourceURL,
	}

	// Set instance info
	var totalDocs int64
	for _, idx := range data.Indexes {
		totalDocs += idx.NumberOfDocuments
	}

	var dbSize int64
	if data.Stats != nil {
		dbSize = data.Stats.DatabaseSize
	}

	r.Instance = Instance{
		Version:        data.Version,
		IndexCount:     len(data.Indexes),
		TotalDocuments: totalDocs,
		DatabaseSize:   dbSize,
	}

	// Calculate summary
	r.Summary = calculateSummary(findings)

	// Sort findings by severity
	sortFindings(findings)

	return r
}

func calculateSummary(findings []*finding.Finding) Summary {
	s := Summary{
		TotalFindings: len(findings),
	}

	for _, f := range findings {
		switch f.Severity {
		case finding.SeverityCritical:
			s.CriticalCount++
		case finding.SeverityWarning:
			s.WarningCount++
		case finding.SeveritySuggestion:
			s.SuggestionCount++
		case finding.SeverityInfo:
			s.InfoCount++
		}
	}

	// Calculate health score (0-100)
	// Start at 100, deduct points for findings
	s.HealthScore = 100
	s.HealthScore -= s.CriticalCount * 25  // Critical issues heavily penalize
	s.HealthScore -= s.WarningCount * 10   // Warnings moderately penalize
	s.HealthScore -= s.SuggestionCount * 3 // Suggestions slightly penalize
	s.HealthScore -= s.InfoCount * 1       // Info minimally penalizes

	if s.HealthScore < 0 {
		s.HealthScore = 0
	}

	// Set status
	switch {
	case s.CriticalCount > 0 || s.HealthScore < 40:
		s.HealthStatus = "critical"
	case s.WarningCount > 0 || s.HealthScore < 70:
		s.HealthStatus = "warning"
	default:
		s.HealthStatus = "healthy"
	}

	return s
}

func sortFindings(findings []*finding.Finding) {
	sort.Slice(findings, func(i, j int) bool {
		// Sort by severity (highest first), then by index, then by ID
		if findings[i].Severity != findings[j].Severity {
			return findings[i].Severity.Weight() > findings[j].Severity.Weight()
		}
		if findings[i].IndexUID != findings[j].IndexUID {
			return findings[i].IndexUID < findings[j].IndexUID
		}
		return findings[i].ID < findings[j].ID
	})
}
