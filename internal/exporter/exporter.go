// Package exporter provides report export functionality.
package exporter

import (
	"github.com/asabla/meiliscan/internal/report"
)

// Exporter defines the interface for report exporters.
type Exporter interface {
	// Export converts a report to the output format.
	Export(r *report.Report) ([]byte, error)
}
