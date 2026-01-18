package analyzer

import (
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
)

func TestDocumentAnalyzer_D002_SchemaConsistency(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "inconsistent fields",
			docs: func() []map[string]interface{} {
				// Create 10 docs where "optional" appears in only half
				docs := make([]map[string]interface{}, 10)
				for i := 0; i < 10; i++ {
					docs[i] = map[string]interface{}{"id": i, "name": "test"}
					if i < 5 {
						docs[i]["optional"] = "value"
					}
				}
				return docs
			}(),
			wantFinding: true,
		},
		{
			name: "consistent schema",
			docs: func() []map[string]interface{} {
				docs := make([]map[string]interface{}, 10)
				for i := 0; i < 10; i++ {
					docs[i] = map[string]interface{}{"id": i, "name": "test"}
				}
				return docs
			}(),
			wantFinding: false,
		},
		{
			name:        "not enough samples",
			docs:        []map[string]interface{}{{"id": 1}},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings:        &collector.IndexSettings{},
			}

			f := analyzer.checkSchemaConsistency(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

func TestDocumentAnalyzer_D004_ArraySizes(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "large arrays",
			docs: []map[string]interface{}{
				{
					"id":   1,
					"tags": make([]interface{}, 100), // 100 elements
				},
			},
			wantFinding: true,
		},
		{
			name: "small arrays",
			docs: []map[string]interface{}{
				{
					"id":   1,
					"tags": []interface{}{"a", "b", "c"},
				},
			},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings:        &collector.IndexSettings{},
			}

			f := analyzer.checkArraySizes(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

func TestDocumentAnalyzer_D005_MarkupContent(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "HTML content",
			docs: []map[string]interface{}{
				{"id": 1, "content": "<p>This is some HTML content</p>"},
			},
			wantFinding: true,
		},
		{
			name: "Markdown content",
			docs: []map[string]interface{}{
				{"id": 1, "content": "Check out [this link](https://example.com)"},
			},
			wantFinding: true,
		},
		{
			name: "plain text",
			docs: []map[string]interface{}{
				{"id": 1, "content": "This is plain text without markup"},
			},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings:        &collector.IndexSettings{},
			}

			f := analyzer.checkMarkupContent(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

func TestDocumentAnalyzer_D007_MixedTypes(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "mixed string and number",
			docs: []map[string]interface{}{
				{"id": 1, "value": "string"},
				{"id": 2, "value": 123},
			},
			wantFinding: true,
		},
		{
			name: "int and float - OK",
			docs: []map[string]interface{}{
				{"id": 1, "value": 123},
				{"id": 2, "value": 123.45},
			},
			wantFinding: false, // int/float mixing is acceptable
		},
		{
			name: "consistent types",
			docs: []map[string]interface{}{
				{"id": 1, "value": "string1"},
				{"id": 2, "value": "string2"},
			},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings:        &collector.IndexSettings{},
			}

			f := analyzer.checkMixedTypes(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

func TestDocumentAnalyzer_D011_ArraysOfObjects(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		filterable  []string
		wantFinding bool
		wantWarning bool
	}{
		{
			name: "arrays of objects - not filterable",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"items": []interface{}{
						map[string]interface{}{"name": "a"},
						map[string]interface{}{"name": "b"},
					},
				},
			},
			filterable:  []string{},
			wantFinding: true,
			wantWarning: false, // info level
		},
		{
			name: "arrays of objects - filterable",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"items": []interface{}{
						map[string]interface{}{"name": "a"},
					},
				},
			},
			filterable:  []string{"items"},
			wantFinding: true,
			wantWarning: true, // warning level
		},
		{
			name: "arrays of primitives - OK",
			docs: []map[string]interface{}{
				{
					"id":   1,
					"tags": []interface{}{"a", "b", "c"},
				},
			},
			filterable:  []string{},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings: &collector.IndexSettings{
					FilterableAttributes: tt.filterable,
				},
			}

			f := analyzer.checkArraysOfObjects(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
			if tt.wantWarning && f != nil && f.Severity != "warning" {
				t.Errorf("expected warning severity, got: %s", f.Severity)
			}
		})
	}
}

func TestDocumentAnalyzer_D012_GeoCoordinates(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "lat/lng separate fields",
			docs: []map[string]interface{}{
				{"id": 1, "lat": 45.5, "lng": -73.6},
			},
			wantFinding: true,
		},
		{
			name: "nested location object",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"location": map[string]interface{}{
						"lat": 45.5,
						"lng": -73.6,
					},
				},
			},
			wantFinding: true,
		},
		{
			name: "proper _geo format - OK",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"_geo": map[string]interface{}{
						"lat": 45.5,
						"lng": -73.6,
					},
				},
			},
			wantFinding: false,
		},
		{
			name: "no geo data",
			docs: []map[string]interface{}{
				{"id": 1, "name": "test"},
			},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings:        &collector.IndexSettings{},
			}

			f := analyzer.checkGeoCoordinates(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

func TestDocumentAnalyzer_D013_DateStrings(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		sortable    []string
		wantFinding bool
	}{
		{
			name: "date string in sortable",
			docs: []map[string]interface{}{
				{"id": 1, "created_at": "2024-01-15T10:30:00"},
			},
			sortable:    []string{"created_at"},
			wantFinding: true,
		},
		{
			name: "date string not sortable",
			docs: []map[string]interface{}{
				{"id": 1, "created_at": "2024-01-15T10:30:00"},
				{"id": 2, "updated_at": "2024-01-16T10:30:00"},
			},
			sortable:    []string{},
			wantFinding: true, // info level with 2+ date fields
		},
		{
			name: "no date fields",
			docs: []map[string]interface{}{
				{"id": 1, "name": "test"},
			},
			sortable:    []string{},
			wantFinding: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			analyzer := NewDocumentAnalyzer()
			idx := collector.IndexData{
				UID:             "test",
				SampleDocuments: tt.docs,
				Settings: &collector.IndexSettings{
					SortableAttributes: tt.sortable,
				},
			}

			f := analyzer.checkDateStrings(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}
