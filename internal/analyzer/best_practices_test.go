package analyzer

import (
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/collector"
)

func TestBestPracticesAnalyzer_B002_DuplicateSearchableFilterable(t *testing.T) {
	analyzer := NewBestPracticesAnalyzer()

	tests := []struct {
		name       string
		data       *collector.CollectedData
		wantCount  int
		wantFindID string
	}{
		{
			name: "duplicates found",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID: "test-index",
						Settings: &collector.IndexSettings{
							SearchableAttributes: []string{"title", "description", "category"},
							FilterableAttributes: []string{"category", "price", "status"},
						},
					},
				},
			},
			wantCount:  1,
			wantFindID: "MEILI-B002",
		},
		{
			name: "no duplicates",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID: "test-index",
						Settings: &collector.IndexSettings{
							SearchableAttributes: []string{"title", "description"},
							FilterableAttributes: []string{"category", "price"},
						},
					},
				},
			},
			wantCount: 0,
		},
		{
			name: "wildcard searchable skipped",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID: "test-index",
						Settings: &collector.IndexSettings{
							SearchableAttributes: []string{"*"},
							FilterableAttributes: []string{"category", "price"},
						},
					},
				},
			},
			wantCount: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			findings := analyzer.Analyze(tt.data)

			// Filter to B002 findings only
			var b002Findings int
			for _, f := range findings {
				if f.ID == "MEILI-B002" {
					b002Findings++
				}
			}

			if b002Findings != tt.wantCount {
				t.Errorf("got %d B002 findings, want %d", b002Findings, tt.wantCount)
			}
		})
	}
}

func TestBestPracticesAnalyzer_B001_SettingsAfterDocuments(t *testing.T) {
	analyzer := NewBestPracticesAnalyzer()

	now := time.Now()
	earlier := now.Add(-1 * time.Hour)
	later := now.Add(1 * time.Hour)

	tests := []struct {
		name       string
		data       *collector.CollectedData
		wantCount  int
		wantFindID string
	}{
		{
			name: "settings after documents",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{UID: "test-index", Settings: &collector.IndexSettings{}},
				},
				Tasks: []collector.Task{
					{IndexUID: "test-index", Type: "documentAdditionOrUpdate", EnqueuedAt: &earlier},
					{IndexUID: "test-index", Type: "settingsUpdate", EnqueuedAt: &later},
				},
			},
			wantCount:  1,
			wantFindID: "MEILI-B001",
		},
		{
			name: "settings before documents - OK",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{UID: "test-index", Settings: &collector.IndexSettings{}},
				},
				Tasks: []collector.Task{
					{IndexUID: "test-index", Type: "settingsUpdate", EnqueuedAt: &earlier},
					{IndexUID: "test-index", Type: "documentAdditionOrUpdate", EnqueuedAt: &later},
				},
			},
			wantCount: 0,
		},
		{
			name: "no tasks",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{UID: "test-index", Settings: &collector.IndexSettings{}},
				},
				Tasks: nil,
			},
			wantCount: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			findings := analyzer.Analyze(tt.data)

			var b001Findings int
			for _, f := range findings {
				if f.ID == "MEILI-B001" {
					b001Findings++
				}
			}

			if b001Findings != tt.wantCount {
				t.Errorf("got %d B001 findings, want %d", b001Findings, tt.wantCount)
			}
		})
	}
}

func TestBestPracticesAnalyzer_B003_MissingEmbedders(t *testing.T) {
	analyzer := NewBestPracticesAnalyzer()

	tests := []struct {
		name       string
		data       *collector.CollectedData
		wantCount  int
		wantFindID string
	}{
		{
			name: "text-heavy index detected",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:               "articles",
						NumberOfDocuments: 500,
						Settings:          &collector.IndexSettings{},
						FieldDistribution: map[string]int64{
							"title":       500,
							"content":     500,
							"description": 500,
						},
					},
				},
			},
			wantCount:  1,
			wantFindID: "MEILI-B003",
		},
		{
			name: "small index - skip",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:               "small",
						NumberOfDocuments: 50, // Less than 100
						Settings:          &collector.IndexSettings{},
						FieldDistribution: map[string]int64{
							"content": 50,
						},
					},
				},
			},
			wantCount: 0,
		},
		{
			name: "no text-heavy fields",
			data: &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:               "products",
						NumberOfDocuments: 1000,
						Settings:          &collector.IndexSettings{},
						FieldDistribution: map[string]int64{
							"name":     1000,
							"price":    1000,
							"category": 1000,
						},
					},
				},
			},
			wantCount: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			findings := analyzer.Analyze(tt.data)

			var b003Findings int
			for _, f := range findings {
				if f.ID == "MEILI-B003" {
					b003Findings++
				}
			}

			if b003Findings != tt.wantCount {
				t.Errorf("got %d B003 findings, want %d", b003Findings, tt.wantCount)
			}
		})
	}
}

func TestBestPracticesAnalyzer_B004_OutdatedVersion(t *testing.T) {
	analyzer := NewBestPracticesAnalyzer()

	tests := []struct {
		name         string
		data         *collector.CollectedData
		wantCount    int
		wantFindID   string
		wantSeverity string
	}{
		{
			name: "major version behind - warning",
			data: &collector.CollectedData{
				Version: "0.30.0",
				Indexes: []collector.IndexData{},
			},
			wantCount:    1,
			wantFindID:   "MEILI-B004",
			wantSeverity: "warning",
		},
		{
			name: "minor version behind - suggestion",
			data: &collector.CollectedData{
				Version: "1.10.0",
				Indexes: []collector.IndexData{},
			},
			wantCount:    1,
			wantFindID:   "MEILI-B004",
			wantSeverity: "suggestion",
		},
		{
			name: "current version - OK",
			data: &collector.CollectedData{
				Version: CurrentStableVersion,
				Indexes: []collector.IndexData{},
			},
			wantCount: 0,
		},
		{
			name: "no version info",
			data: &collector.CollectedData{
				Version: "",
				Indexes: []collector.IndexData{},
			},
			wantCount: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			findings := analyzer.Analyze(tt.data)

			var b004Findings int
			for _, f := range findings {
				if f.ID == "MEILI-B004" {
					b004Findings++
					if tt.wantSeverity != "" && string(f.Severity) != tt.wantSeverity {
						t.Errorf("got severity %s, want %s", f.Severity, tt.wantSeverity)
					}
				}
			}

			if b004Findings != tt.wantCount {
				t.Errorf("got %d B004 findings, want %d", b004Findings, tt.wantCount)
			}
		})
	}
}

func TestParseVersion(t *testing.T) {
	tests := []struct {
		input string
		want  []int
	}{
		{"1.12.0", []int{1, 12, 0}},
		{"0.30.5", []int{0, 30, 5}},
		{"1.0.0-rc1", []int{1, 0, 0}},
		{"v1.12.0", []int{1, 12, 0}}, // parseVersion is called after trimming 'v'
		{"invalid", []int{}},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := parseVersion(tt.input)
			if len(got) != len(tt.want) {
				t.Errorf("parseVersion(%q) = %v, want %v", tt.input, got, tt.want)
				return
			}
			for i := range got {
				if got[i] != tt.want[i] {
					t.Errorf("parseVersion(%q) = %v, want %v", tt.input, got, tt.want)
					return
				}
			}
		})
	}
}
