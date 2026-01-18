package analyzer

import (
	"fmt"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// PerformanceAnalyzer analyzes performance-related aspects.
type PerformanceAnalyzer struct{}

// NewPerformanceAnalyzer creates a new PerformanceAnalyzer.
func NewPerformanceAnalyzer() *PerformanceAnalyzer {
	return &PerformanceAnalyzer{}
}

// Name returns the analyzer name.
func (a *PerformanceAnalyzer) Name() string {
	return "performance"
}

// Analyze runs performance analysis on the collected data.
func (a *PerformanceAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	// P004: Too many indexes
	if f := a.checkTooManyIndexes(data); f != nil {
		findings = append(findings, f)
	}

	return findings
}

// P004: Too many indexes
func (a *PerformanceAnalyzer) checkTooManyIndexes(data *collector.CollectedData) *finding.Finding {
	const threshold = 50

	if len(data.Indexes) >= threshold {
		f := finding.New(
			"MEILI-P004",
			"Too many indexes",
			fmt.Sprintf("Instance has %d indexes. Large numbers of indexes can impact memory usage and startup time.", len(data.Indexes)),
			finding.SeveritySuggestion,
			finding.CategoryPerformance,
		).WithRecommendation("Consider consolidating related data into fewer indexes using filterable attributes for segmentation.").
			WithDetails(map[string]interface{}{
				"index_count": len(data.Indexes),
				"threshold":   threshold,
			})

		return f
	}

	return nil
}
