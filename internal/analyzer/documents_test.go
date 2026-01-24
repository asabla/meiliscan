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

// D009: Sensitive field names detection
func TestDocumentAnalyzer_D009_SensitiveFieldNames(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "email field detected",
			docs: []map[string]interface{}{
				{"id": 1, "email": "user@example.com", "name": "John"},
			},
			wantFinding: true,
		},
		{
			name: "password field detected",
			docs: []map[string]interface{}{
				{"id": 1, "username": "john", "password": "secret123"},
			},
			wantFinding: true,
		},
		{
			name: "phone field detected",
			docs: []map[string]interface{}{
				{"id": 1, "name": "John", "phone": "555-1234"},
			},
			wantFinding: true,
		},
		{
			name: "nested sensitive field",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"user": map[string]interface{}{
						"name":  "John",
						"email": "john@example.com",
					},
				},
			},
			wantFinding: true,
		},
		{
			name: "ssn field detected",
			docs: []map[string]interface{}{
				{"id": 1, "ssn": "123-45-6789"},
			},
			wantFinding: true,
		},
		{
			name: "api_key field detected",
			docs: []map[string]interface{}{
				{"id": 1, "api_key": "sk_live_123456"},
			},
			wantFinding: true,
		},
		{
			name: "no sensitive fields",
			docs: []map[string]interface{}{
				{"id": 1, "title": "Product", "description": "A great product"},
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

			f := analyzer.checkSensitiveFieldNames(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

// D010: PII content detection
func TestDocumentAnalyzer_D010_PIIContent(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "email pattern detected",
			docs: []map[string]interface{}{
				{"id": 1, "contact": "user@example.com"},
			},
			wantFinding: true,
		},
		{
			name: "phone pattern detected",
			docs: []map[string]interface{}{
				{"id": 1, "info": "Call me at 555-123-4567"},
			},
			wantFinding: true,
		},
		{
			name: "SSN pattern detected",
			docs: []map[string]interface{}{
				{"id": 1, "data": "SSN: 123-45-6789"},
			},
			wantFinding: true,
		},
		{
			name: "credit card pattern detected",
			docs: []map[string]interface{}{
				{"id": 1, "payment": "Card: 4111-1111-1111-1111"},
			},
			wantFinding: true,
		},
		{
			name: "IP address pattern detected",
			docs: []map[string]interface{}{
				{"id": 1, "log": "Request from 192.168.1.100"},
			},
			wantFinding: true,
		},
		{
			name: "nested PII content",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"user": map[string]interface{}{
						"info": "Contact: admin@company.org",
					},
				},
			},
			wantFinding: true,
		},
		{
			name: "PII in array",
			docs: []map[string]interface{}{
				{
					"id":     1,
					"emails": []interface{}{"user1@test.com", "user2@test.com"},
				},
			},
			wantFinding: true,
		},
		{
			name: "no PII content",
			docs: []map[string]interface{}{
				{"id": 1, "title": "Product Name", "price": 99.99},
			},
			wantFinding: false,
		},
		{
			name: "short strings ignored",
			docs: []map[string]interface{}{
				{"id": 1, "code": "AB12"}, // too short to scan
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

			f := analyzer.checkPIIContent(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

// D001: Large document size detection
func TestDocumentAnalyzer_D001_DocumentSize(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "large document detected",
			docs: []map[string]interface{}{
				{
					"id":      1,
					"content": string(make([]byte, 150*1024)), // 150KB string
				},
			},
			wantFinding: true,
		},
		{
			name: "average size too large",
			docs: func() []map[string]interface{} {
				docs := make([]map[string]interface{}, 5)
				for i := 0; i < 5; i++ {
					docs[i] = map[string]interface{}{
						"id":      i,
						"content": string(make([]byte, 15*1024)), // 15KB each
					}
				}
				return docs
			}(),
			wantFinding: true,
		},
		{
			name: "small documents OK",
			docs: []map[string]interface{}{
				{"id": 1, "title": "Short title", "desc": "Short description"},
				{"id": 2, "title": "Another title", "desc": "Another description"},
			},
			wantFinding: false,
		},
		{
			name:        "empty documents",
			docs:        []map[string]interface{}{},
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

			f := analyzer.checkDocumentSize(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

// D003: Nesting depth detection
func TestDocumentAnalyzer_D003_NestingDepth(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "deep nesting detected",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"level1": map[string]interface{}{
						"level2": map[string]interface{}{
							"level3": map[string]interface{}{
								"level4": map[string]interface{}{
									"data": "deeply nested",
								},
							},
						},
					},
				},
			},
			wantFinding: true,
		},
		{
			name: "acceptable nesting depth",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"level1": map[string]interface{}{
						"level2": map[string]interface{}{
							"data": "OK depth",
						},
					},
				},
			},
			wantFinding: false,
		},
		{
			name: "flat document",
			docs: []map[string]interface{}{
				{"id": 1, "title": "Flat", "price": 100},
			},
			wantFinding: false,
		},
		{
			name: "empty nested objects",
			docs: []map[string]interface{}{
				{
					"id":    1,
					"empty": map[string]interface{}{},
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

			f := analyzer.checkNestingDepth(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

// D006: Empty fields detection
func TestDocumentAnalyzer_D006_EmptyFields(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "high empty ratio detected",
			docs: []map[string]interface{}{
				{"id": 1, "name": "John", "nickname": nil},
				{"id": 2, "name": "Jane", "nickname": nil},
				{"id": 3, "name": "Bob", "nickname": ""},
				{"id": 4, "name": "Alice", "nickname": nil},
				{"id": 5, "name": "Eve", "nickname": "Evie"},
			},
			wantFinding: true, // 4/5 = 80% empty for nickname
		},
		{
			name: "empty string fields",
			docs: []map[string]interface{}{
				{"id": 1, "title": "Product", "description": ""},
				{"id": 2, "title": "Product2", "description": ""},
				{"id": 3, "title": "Product3", "description": ""},
				{"id": 4, "title": "Product4", "description": "Has desc"},
			},
			wantFinding: true, // 75% empty
		},
		{
			name: "empty arrays",
			docs: []map[string]interface{}{
				{"id": 1, "tags": []interface{}{}},
				{"id": 2, "tags": []interface{}{}},
				{"id": 3, "tags": []interface{}{"a", "b"}},
			},
			wantFinding: true, // 66% empty
		},
		{
			name: "empty nested objects",
			docs: []map[string]interface{}{
				{"id": 1, "meta": map[string]interface{}{}},
				{"id": 2, "meta": map[string]interface{}{}},
				{"id": 3, "meta": map[string]interface{}{"key": "value"}},
			},
			wantFinding: true,
		},
		{
			name: "low empty ratio OK",
			docs: []map[string]interface{}{
				{"id": 1, "name": "John", "email": "john@test.com"},
				{"id": 2, "name": "Jane", "email": "jane@test.com"},
				{"id": 3, "name": "Bob", "email": "bob@test.com"},
				{"id": 4, "name": "Alice", "email": nil}, // only 1/4 empty = 25%
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

			f := analyzer.checkEmptyFields(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

// D008: Long text fields detection
func TestDocumentAnalyzer_D008_TextLength(t *testing.T) {
	tests := []struct {
		name        string
		docs        []map[string]interface{}
		wantFinding bool
	}{
		{
			name: "very long text detected",
			docs: []map[string]interface{}{
				{
					"id":      1,
					"content": string(make([]byte, 70000)), // > 65535
				},
			},
			wantFinding: true,
		},
		{
			name: "nested long text detected",
			docs: []map[string]interface{}{
				{
					"id": 1,
					"article": map[string]interface{}{
						"body": string(make([]byte, 70000)),
					},
				},
			},
			wantFinding: true,
		},
		{
			name: "acceptable text length",
			docs: []map[string]interface{}{
				{
					"id":      1,
					"content": string(make([]byte, 5000)), // < 65535
				},
			},
			wantFinding: false,
		},
		{
			name: "short text fields",
			docs: []map[string]interface{}{
				{"id": 1, "title": "Short title", "description": "Short desc"},
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

			f := analyzer.checkTextLength(idx)
			if tt.wantFinding && f == nil {
				t.Error("expected finding but got nil")
			}
			if !tt.wantFinding && f != nil {
				t.Errorf("expected no finding but got: %s", f.ID)
			}
		})
	}
}

// Test helper functions directly
func TestHelperFunction_EstimateDocSize(t *testing.T) {
	tests := []struct {
		name    string
		doc     interface{}
		minSize int64
	}{
		{
			name:    "empty object",
			doc:     map[string]interface{}{},
			minSize: 2,
		},
		{
			name:    "simple string",
			doc:     "hello",
			minSize: 7, // 5 chars + 2 quotes
		},
		{
			name:    "number",
			doc:     42.0,
			minSize: 8,
		},
		{
			name:    "boolean",
			doc:     true,
			minSize: 5,
		},
		{
			name:    "null",
			doc:     nil,
			minSize: 4,
		},
		{
			name:    "array",
			doc:     []interface{}{"a", "b"},
			minSize: 2,
		},
		{
			name: "nested object",
			doc: map[string]interface{}{
				"name": "test",
			},
			minSize: 10,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			size := estimateDocSize(tt.doc)
			if size < tt.minSize {
				t.Errorf("expected size >= %d, got %d", tt.minSize, size)
			}
		})
	}
}

func TestHelperFunction_GetMaxDepth(t *testing.T) {
	tests := []struct {
		name          string
		doc           interface{}
		expectedDepth int
	}{
		{
			name:          "flat object",
			doc:           map[string]interface{}{"a": 1, "b": 2},
			expectedDepth: 1,
		},
		{
			name: "nested object",
			doc: map[string]interface{}{
				"level1": map[string]interface{}{
					"level2": "value",
				},
			},
			expectedDepth: 2,
		},
		{
			name: "deeply nested",
			doc: map[string]interface{}{
				"a": map[string]interface{}{
					"b": map[string]interface{}{
						"c": map[string]interface{}{
							"d": "deep",
						},
					},
				},
			},
			expectedDepth: 4,
		},
		{
			name:          "array does not add depth",
			doc:           []interface{}{"a", "b", "c"},
			expectedDepth: 0,
		},
		{
			name: "array with objects",
			doc: []interface{}{
				map[string]interface{}{"a": 1},
				map[string]interface{}{"b": 2},
			},
			expectedDepth: 1,
		},
		{
			name:          "empty object",
			doc:           map[string]interface{}{},
			expectedDepth: 0,
		},
		{
			name:          "primitive",
			doc:           "string",
			expectedDepth: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			depth := getMaxDepth(tt.doc, 0)
			if depth != tt.expectedDepth {
				t.Errorf("expected depth %d, got %d", tt.expectedDepth, depth)
			}
		})
	}
}

func TestHelperFunction_ScanForPII(t *testing.T) {
	tests := []struct {
		name       string
		obj        interface{}
		wantFields int
	}{
		{
			name:       "email detected",
			obj:        map[string]interface{}{"contact": "user@example.com"},
			wantFields: 1,
		},
		{
			name:       "multiple PII types",
			obj:        map[string]interface{}{"email": "a@b.com", "phone": "555-123-4567"},
			wantFields: 2,
		},
		{
			name: "nested PII",
			obj: map[string]interface{}{
				"user": map[string]interface{}{
					"email": "nested@test.com",
				},
			},
			wantFields: 1,
		},
		{
			name: "PII in array",
			obj: map[string]interface{}{
				"emails": []interface{}{"a@b.com", "c@d.com"},
			},
			wantFields: 1,
		},
		{
			name:       "no PII",
			obj:        map[string]interface{}{"title": "Product", "price": 100},
			wantFields: 0,
		},
		{
			name:       "short string ignored",
			obj:        map[string]interface{}{"code": "AB"},
			wantFields: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			detections := make(map[string][]string)
			scanForPII(tt.obj, "", detections)
			if len(detections) != tt.wantFields {
				t.Errorf("expected %d fields with PII, got %d", tt.wantFields, len(detections))
			}
		})
	}
}

func TestHelperFunction_CountEmptyFields(t *testing.T) {
	tests := []struct {
		name            string
		obj             interface{}
		wantEmptyFields int
	}{
		{
			name:            "nil value",
			obj:             map[string]interface{}{"field": nil},
			wantEmptyFields: 1,
		},
		{
			name:            "empty string",
			obj:             map[string]interface{}{"field": ""},
			wantEmptyFields: 1,
		},
		{
			name:            "empty array",
			obj:             map[string]interface{}{"arr": []interface{}{}},
			wantEmptyFields: 1,
		},
		{
			name:            "empty map",
			obj:             map[string]interface{}{"obj": map[string]interface{}{}},
			wantEmptyFields: 1,
		},
		{
			name:            "non-empty values",
			obj:             map[string]interface{}{"field": "value", "num": 42},
			wantEmptyFields: 0,
		},
		{
			name: "nested empty",
			obj: map[string]interface{}{
				"nested": map[string]interface{}{
					"empty": nil,
				},
			},
			wantEmptyFields: 1,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			emptyCounts := make(map[string]int)
			totalCounts := make(map[string]int)
			countEmptyFields(tt.obj, "", emptyCounts, totalCounts)

			totalEmpty := 0
			for _, count := range emptyCounts {
				totalEmpty += count
			}

			if totalEmpty != tt.wantEmptyFields {
				t.Errorf("expected %d empty fields, got %d", tt.wantEmptyFields, totalEmpty)
			}
		})
	}
}

func TestHelperFunction_FindLongText(t *testing.T) {
	tests := []struct {
		name           string
		obj            interface{}
		wantLongFields int
	}{
		{
			name:           "long text found",
			obj:            map[string]interface{}{"content": string(make([]byte, 70000))},
			wantLongFields: 1,
		},
		{
			name: "nested long text",
			obj: map[string]interface{}{
				"article": map[string]interface{}{
					"body": string(make([]byte, 70000)),
				},
			},
			wantLongFields: 1,
		},
		{
			name:           "short text OK",
			obj:            map[string]interface{}{"content": "short text"},
			wantLongFields: 0,
		},
		{
			name:           "exactly at threshold",
			obj:            map[string]interface{}{"content": string(make([]byte, 65535))},
			wantLongFields: 0, // must be > 65535
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			longFields := make(map[string]int)
			findLongText(tt.obj, "", longFields)

			if len(longFields) != tt.wantLongFields {
				t.Errorf("expected %d long fields, got %d", tt.wantLongFields, len(longFields))
			}
		})
	}
}
