package exporter

import (
	"encoding/json"

	"github.com/asabla/meiliscan/internal/report"
)

// JSONExporter exports reports as JSON.
type JSONExporter struct {
	indent bool
}

// NewJSON creates a new JSONExporter with indentation enabled.
func NewJSON() *JSONExporter {
	return &JSONExporter{indent: true}
}

// Export converts the report to JSON.
func (e *JSONExporter) Export(r *report.Report) ([]byte, error) {
	if e.indent {
		return json.MarshalIndent(r, "", "  ")
	}
	return json.Marshal(r)
}
