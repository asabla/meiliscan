// Package analyzer provides the analysis framework and individual analyzers.
package analyzer

import (
	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// Analyzer defines the interface for analysis components.
type Analyzer interface {
	// Name returns the analyzer name.
	Name() string

	// Analyze runs the analysis and returns findings.
	Analyze(data *collector.CollectedData) []*finding.Finding
}

// Registry holds all registered analyzers.
type Registry struct {
	analyzers []Analyzer
}

// NewRegistry creates a new Registry with default analyzers.
func NewRegistry() *Registry {
	r := &Registry{}

	// Register default analyzers
	r.Register(NewSchemaAnalyzer())
	r.Register(NewPerformanceAnalyzer())
	r.Register(NewDocumentAnalyzer())
	r.Register(NewInstanceAnalyzer())

	return r
}

// Register adds an analyzer to the registry.
func (r *Registry) Register(a Analyzer) {
	r.analyzers = append(r.analyzers, a)
}

// Analyze runs all registered analyzers and returns combined findings.
func (r *Registry) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	for _, a := range r.analyzers {
		findings = append(findings, a.Analyze(data)...)
	}

	return findings
}
