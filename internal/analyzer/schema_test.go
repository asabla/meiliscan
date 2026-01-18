package analyzer

import (
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

func TestSchemaAnalyzer_WildcardSearchable(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "wildcard searchable triggers S001",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"*"},
			},
			expectFound: true,
		},
		{
			name: "explicit attributes does not trigger S001",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title", "description"},
			},
			expectFound: false,
		},
		{
			name:        "nil settings does not trigger S001",
			settings:    nil,
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:      "test-index",
						Settings: tt.settings,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S001" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S001 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

func TestSchemaAnalyzer_IDFieldsSearchable(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "user_id in searchable triggers S002",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title", "user_id"},
			},
			expectFound: true,
		},
		{
			name: "uuid in searchable triggers S002",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"uuid", "name"},
			},
			expectFound: true,
		},
		{
			name: "no ID fields does not trigger S002",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title", "description"},
			},
			expectFound: false,
		},
		{
			name: "wildcard searchable does not trigger S002 (caught by S001)",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"*"},
			},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:      "test-index",
						Settings: tt.settings,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S002" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S002 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

func TestSchemaAnalyzer_EmptyFilterable(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "empty filterable triggers S004",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				FilterableAttributes: []string{},
			},
			expectFound: true,
		},
		{
			name: "has filterable does not trigger S004",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				FilterableAttributes: []string{"category"},
			},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:      "test-index",
						Settings: tt.settings,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S004" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S004 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

func TestSchemaAnalyzer_DefaultRankingRules(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	defaultRules := []string{"words", "typo", "proximity", "attribute", "sort", "exactness"}

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "default rules triggers S007",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				RankingRules:         defaultRules,
			},
			expectFound: true,
		},
		{
			name: "custom rules does not trigger S007",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				RankingRules:         []string{"words", "typo", "sort:popularity:desc", "proximity", "attribute", "exactness"},
			},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:      "test-index",
						Settings: tt.settings,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S007" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S007 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

func TestFindingSeverityWeight(t *testing.T) {
	tests := []struct {
		severity finding.Severity
		expected int
	}{
		{finding.SeverityCritical, 4},
		{finding.SeverityWarning, 3},
		{finding.SeveritySuggestion, 2},
		{finding.SeverityInfo, 1},
	}

	for _, tt := range tests {
		t.Run(string(tt.severity), func(t *testing.T) {
			if got := tt.severity.Weight(); got != tt.expected {
				t.Errorf("expected weight %d, got %d", tt.expected, got)
			}
		})
	}
}
