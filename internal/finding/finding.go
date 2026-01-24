// Package finding defines the Finding model and severity/category types.
package finding

import "time"

// Severity represents the severity level of a finding.
type Severity string

const (
	SeverityCritical   Severity = "critical"
	SeverityWarning    Severity = "warning"
	SeveritySuggestion Severity = "suggestion"
	SeverityInfo       Severity = "info"
)

// Category represents the category of a finding.
type Category string

const (
	CategorySchema       Category = "schema"
	CategoryDocument     Category = "document"
	CategoryPerformance  Category = "performance"
	CategoryBestPractice Category = "best_practice"
	CategoryInstance     Category = "instance"
	CategorySearchProbe  Category = "search_probe"
)

// Finding represents a single analysis finding.
type Finding struct {
	// ID is the unique identifier for this finding type (e.g., "MEILI-S001")
	ID string `json:"id"`

	// Title is a short description of the finding
	Title string `json:"title"`

	// Description is a detailed explanation of the finding
	Description string `json:"description"`

	// Severity indicates how serious the finding is
	Severity Severity `json:"severity"`

	// Category groups related findings
	Category Category `json:"category"`

	// IndexUID is the index this finding applies to (empty if global)
	IndexUID string `json:"index_uid,omitempty"`

	// Details contains additional context-specific information
	Details map[string]interface{} `json:"details,omitempty"`

	// Recommendation provides actionable advice to resolve the finding
	Recommendation string `json:"recommendation,omitempty"`

	// FixCommand is an optional API command to fix the issue
	FixCommand string `json:"fix_command,omitempty"`

	// Timestamp is when the finding was generated
	Timestamp time.Time `json:"timestamp"`
}

// New creates a new Finding with the given parameters.
func New(id, title, description string, severity Severity, category Category) *Finding {
	return &Finding{
		ID:          id,
		Title:       title,
		Description: description,
		Severity:    severity,
		Category:    category,
		Timestamp:   time.Now(),
		Details:     make(map[string]interface{}),
	}
}

// WithIndex sets the index UID for this finding.
func (f *Finding) WithIndex(uid string) *Finding {
	f.IndexUID = uid
	return f
}

// WithDetails adds details to this finding.
func (f *Finding) WithDetails(details map[string]interface{}) *Finding {
	f.Details = details
	return f
}

// WithRecommendation sets the recommendation for this finding.
func (f *Finding) WithRecommendation(rec string) *Finding {
	f.Recommendation = rec
	return f
}

// WithFixCommand sets the fix command for this finding.
func (f *Finding) WithFixCommand(cmd string) *Finding {
	f.FixCommand = cmd
	return f
}

// SeverityWeight returns a numeric weight for sorting by severity.
func (s Severity) Weight() int {
	switch s {
	case SeverityCritical:
		return 4
	case SeverityWarning:
		return 3
	case SeveritySuggestion:
		return 2
	case SeverityInfo:
		return 1
	default:
		return 0
	}
}
