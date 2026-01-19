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

// S013: No sortable attributes but has sort candidates
func TestSchemaAnalyzer_NoSortableWithCandidates(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		fields      map[string]int64
		expectFound bool
	}{
		{
			name: "no sortable but has date field triggers S013",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				SortableAttributes:   []string{},
			},
			fields:      map[string]int64{"title": 100, "created_at": 100, "updated_at": 100},
			expectFound: true,
		},
		{
			name: "no sortable but has price field triggers S013",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				SortableAttributes:   []string{},
			},
			fields:      map[string]int64{"title": 100, "price": 100},
			expectFound: true,
		},
		{
			name: "sortable configured does not trigger S013",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				SortableAttributes:   []string{"created_at"},
			},
			fields:      map[string]int64{"title": 100, "created_at": 100},
			expectFound: false,
		},
		{
			name: "no sort candidates does not trigger S013",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title"},
				SortableAttributes:   []string{},
			},
			fields:      map[string]int64{"title": 100, "description": 100},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:               "test-index",
						Settings:          tt.settings,
						FieldDistribution: tt.fields,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S013" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S013 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S014: Sortable attribute type issues
func TestSchemaAnalyzer_SortableTypes(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		docs        []map[string]interface{}
		expectFound bool
	}{
		{
			name: "sortable with mixed numeric and string triggers S014",
			settings: &collector.IndexSettings{
				SortableAttributes: []string{"price"},
			},
			docs: []map[string]interface{}{
				{"price": 100.0},
				{"price": "unknown"},
				{"price": 200.0},
			},
			expectFound: true,
		},
		{
			name: "sortable with array type triggers S014",
			settings: &collector.IndexSettings{
				SortableAttributes: []string{"tags"},
			},
			docs: []map[string]interface{}{
				{"tags": []interface{}{"a", "b"}},
				{"tags": []interface{}{"c"}},
			},
			expectFound: true,
		},
		{
			name: "sortable with consistent numeric type does not trigger S014",
			settings: &collector.IndexSettings{
				SortableAttributes: []string{"price"},
			},
			docs: []map[string]interface{}{
				{"price": 100.0},
				{"price": 200.0},
				{"price": 300.0},
			},
			expectFound: false,
		},
		{
			name: "no sample docs does not trigger S014",
			settings: &collector.IndexSettings{
				SortableAttributes: []string{"price"},
			},
			docs:        []map[string]interface{}{},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:             "test-index",
						Settings:        tt.settings,
						SampleDocuments: tt.docs,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S014" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S014 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S015: High-cardinality filterable attributes
func TestSchemaAnalyzer_FilterableCardinality(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		docs        []map[string]interface{}
		expectFound bool
	}{
		{
			name: "filterable with email pattern triggers S015",
			settings: &collector.IndexSettings{
				FilterableAttributes: []string{"user_email"},
			},
			docs:        []map[string]interface{}{},
			expectFound: true,
		},
		{
			name: "filterable with uuid pattern triggers S015",
			settings: &collector.IndexSettings{
				FilterableAttributes: []string{"uuid"},
			},
			docs:        []map[string]interface{}{},
			expectFound: true,
		},
		{
			name: "filterable with high uniqueness triggers S015",
			settings: &collector.IndexSettings{
				FilterableAttributes: []string{"sku"},
			},
			docs: []map[string]interface{}{
				{"sku": "SKU001"},
				{"sku": "SKU002"},
				{"sku": "SKU003"},
				{"sku": "SKU004"},
				{"sku": "SKU005"},
			},
			expectFound: true, // 100% unique
		},
		{
			name: "filterable with low cardinality does not trigger S015",
			settings: &collector.IndexSettings{
				FilterableAttributes: []string{"category"},
			},
			docs: []map[string]interface{}{
				{"category": "electronics"},
				{"category": "electronics"},
				{"category": "books"},
				{"category": "electronics"},
				{"category": "books"},
			},
			expectFound: false, // only 40% unique
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:             "test-index",
						Settings:        tt.settings,
						SampleDocuments: tt.docs,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-S015" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S015 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S016: Faceting maxValuesPerFacet issues
func TestSchemaAnalyzer_FacetingSettings(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "very high maxValuesPerFacet triggers S016",
			settings: &collector.IndexSettings{
				Faceting: &collector.Faceting{
					MaxValuesPerFacet: 1000,
				},
			},
			expectFound: true,
		},
		{
			name: "moderate maxValuesPerFacet does not trigger S016",
			settings: &collector.IndexSettings{
				Faceting: &collector.Faceting{
					MaxValuesPerFacet: 100,
				},
			},
			expectFound: false,
		},
		{
			name: "nil faceting does not trigger S016",
			settings: &collector.IndexSettings{
				Faceting: nil,
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
				if f.ID == "MEILI-S016" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S016 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S017: Synonyms configuration issues
func TestSchemaAnalyzer_Synonyms(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "self-referencing synonym triggers S017",
			settings: &collector.IndexSettings{
				Synonyms: map[string][]string{
					"laptop": {"notebook", "laptop"}, // self-reference
				},
			},
			expectFound: true,
		},
		{
			name: "empty synonym list triggers S017",
			settings: &collector.IndexSettings{
				Synonyms: map[string][]string{
					"laptop": {},
				},
			},
			expectFound: true,
		},
		{
			name: "long synonym chain triggers S017",
			settings: &collector.IndexSettings{
				Synonyms: map[string][]string{
					"laptop": make([]string, 25), // >20 synonyms
				},
			},
			expectFound: true,
		},
		{
			name: "valid synonyms do not trigger S017",
			settings: &collector.IndexSettings{
				Synonyms: map[string][]string{
					"laptop": {"notebook", "portable computer"},
					"phone":  {"mobile", "cellphone"},
				},
			},
			expectFound: false,
		},
		{
			name: "no synonyms does not trigger S017",
			settings: &collector.IndexSettings{
				Synonyms: map[string][]string{},
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
				if f.ID == "MEILI-S017" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S017 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S018: Typo tolerance on ID fields
func TestSchemaAnalyzer_TypoToleranceOnIDs(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "ID field searchable without typo protection triggers S018",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title", "product_id"},
				TypoTolerance: &collector.TypoTolerance{
					Enabled:             true,
					DisableOnAttributes: []string{},
				},
			},
			expectFound: true,
		},
		{
			name: "ID field with typo protection does not trigger S018",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title", "product_id"},
				TypoTolerance: &collector.TypoTolerance{
					Enabled:             true,
					DisableOnAttributes: []string{"product_id"},
				},
			},
			expectFound: false,
		},
		{
			name: "typo tolerance disabled does not trigger S018",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"title", "product_id"},
				TypoTolerance: &collector.TypoTolerance{
					Enabled: false,
				},
			},
			expectFound: false,
		},
		{
			name: "wildcard searchable does not trigger S018",
			settings: &collector.IndexSettings{
				SearchableAttributes: []string{"*"},
				TypoTolerance: &collector.TypoTolerance{
					Enabled: true,
				},
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
				if f.ID == "MEILI-S018" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S018 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S019: Permissive typo tolerance settings
func TestSchemaAnalyzer_PermissiveTypoTolerance(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "very low oneTypo triggers S019",
			settings: &collector.IndexSettings{
				TypoTolerance: &collector.TypoTolerance{
					Enabled: true,
					MinWordSizeForTypos: collector.MinWordSizeForTypos{
						OneTypo:  2,
						TwoTypos: 9,
					},
				},
			},
			expectFound: true,
		},
		{
			name: "very low twoTypos triggers S019",
			settings: &collector.IndexSettings{
				TypoTolerance: &collector.TypoTolerance{
					Enabled: true,
					MinWordSizeForTypos: collector.MinWordSizeForTypos{
						OneTypo:  5,
						TwoTypos: 4,
					},
				},
			},
			expectFound: true,
		},
		{
			name: "default values do not trigger S019",
			settings: &collector.IndexSettings{
				TypoTolerance: &collector.TypoTolerance{
					Enabled: true,
					MinWordSizeForTypos: collector.MinWordSizeForTypos{
						OneTypo:  5,
						TwoTypos: 9,
					},
				},
			},
			expectFound: false,
		},
		{
			name: "typo tolerance disabled does not trigger S019",
			settings: &collector.IndexSettings{
				TypoTolerance: &collector.TypoTolerance{
					Enabled: false,
					MinWordSizeForTypos: collector.MinWordSizeForTypos{
						OneTypo:  1,
						TwoTypos: 2,
					},
				},
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
				if f.ID == "MEILI-S019" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S019 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// S020: Dictionary/tokenization issues
func TestSchemaAnalyzer_DictionarySettings(t *testing.T) {
	analyzer := NewSchemaAnalyzer()

	// Create a large dictionary
	largeDictionary := make([]string, 600)
	for i := range largeDictionary {
		largeDictionary[i] = "word"
	}

	tests := []struct {
		name        string
		settings    *collector.IndexSettings
		expectFound bool
	}{
		{
			name: "large dictionary triggers S020",
			settings: &collector.IndexSettings{
				Dictionary: largeDictionary,
			},
			expectFound: true,
		},
		{
			name: "duplicate dictionary entries triggers S020",
			settings: &collector.IndexSettings{
				Dictionary: []string{"hello", "world", "hello"},
			},
			expectFound: true,
		},
		{
			name: "alphanumeric separator token triggers S020",
			settings: &collector.IndexSettings{
				SeparatorTokens: []string{"abc123"},
			},
			expectFound: true,
		},
		{
			name: "long separator token triggers S020",
			settings: &collector.IndexSettings{
				SeparatorTokens: []string{"------"},
			},
			expectFound: true,
		},
		{
			name: "large non-separator tokens triggers S020",
			settings: &collector.IndexSettings{
				NonSeparatorTokens: make([]string, 150),
			},
			expectFound: true,
		},
		{
			name: "normal punctuation separator does not trigger S020",
			settings: &collector.IndexSettings{
				SeparatorTokens: []string{"-", "_", "."},
			},
			expectFound: false,
		},
		{
			name: "small dictionary does not trigger S020",
			settings: &collector.IndexSettings{
				Dictionary: []string{"C++", "C#", "Node.js"},
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
				if f.ID == "MEILI-S020" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected S020 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}
