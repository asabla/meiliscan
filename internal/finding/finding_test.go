package finding

import (
	"testing"
	"time"
)

func TestNew(t *testing.T) {
	f := New("MEILI-S001", "Test Title", "Test Description", SeverityCritical, CategorySchema)

	if f.ID != "MEILI-S001" {
		t.Errorf("ID = %q, want %q", f.ID, "MEILI-S001")
	}
	if f.Title != "Test Title" {
		t.Errorf("Title = %q, want %q", f.Title, "Test Title")
	}
	if f.Description != "Test Description" {
		t.Errorf("Description = %q, want %q", f.Description, "Test Description")
	}
	if f.Severity != SeverityCritical {
		t.Errorf("Severity = %q, want %q", f.Severity, SeverityCritical)
	}
	if f.Category != CategorySchema {
		t.Errorf("Category = %q, want %q", f.Category, CategorySchema)
	}
	if f.Details == nil {
		t.Error("Details should be initialized to empty map, got nil")
	}
	if f.Timestamp.IsZero() {
		t.Error("Timestamp should be set, got zero time")
	}
	if time.Since(f.Timestamp) > time.Second {
		t.Error("Timestamp should be recent")
	}
}

func TestFinding_WithIndex(t *testing.T) {
	f := New("TEST", "Title", "Desc", SeverityWarning, CategoryDocument)

	result := f.WithIndex("products")

	// Should return same pointer for chaining
	if result != f {
		t.Error("WithIndex should return same pointer")
	}
	if f.IndexUID != "products" {
		t.Errorf("IndexUID = %q, want %q", f.IndexUID, "products")
	}
}

func TestFinding_WithDetails(t *testing.T) {
	f := New("TEST", "Title", "Desc", SeverityWarning, CategoryDocument)

	details := map[string]interface{}{
		"field":       "name",
		"count":       42,
		"is_critical": true,
	}

	result := f.WithDetails(details)

	if result != f {
		t.Error("WithDetails should return same pointer")
	}
	if f.Details["field"] != "name" {
		t.Errorf("Details[field] = %v, want %q", f.Details["field"], "name")
	}
	if f.Details["count"] != 42 {
		t.Errorf("Details[count] = %v, want 42", f.Details["count"])
	}
	if f.Details["is_critical"] != true {
		t.Errorf("Details[is_critical] = %v, want true", f.Details["is_critical"])
	}
}

func TestFinding_WithRecommendation(t *testing.T) {
	f := New("TEST", "Title", "Desc", SeverityInfo, CategoryPerformance)

	result := f.WithRecommendation("Do something better")

	if result != f {
		t.Error("WithRecommendation should return same pointer")
	}
	if f.Recommendation != "Do something better" {
		t.Errorf("Recommendation = %q, want %q", f.Recommendation, "Do something better")
	}
}

func TestFinding_WithFixCommand(t *testing.T) {
	f := New("TEST", "Title", "Desc", SeveritySuggestion, CategoryBestPractice)

	result := f.WithFixCommand("curl -X PATCH ...")

	if result != f {
		t.Error("WithFixCommand should return same pointer")
	}
	if f.FixCommand != "curl -X PATCH ..." {
		t.Errorf("FixCommand = %q, want %q", f.FixCommand, "curl -X PATCH ...")
	}
}

func TestFinding_FluentChaining(t *testing.T) {
	f := New("MEILI-S001", "Test", "Description", SeverityCritical, CategorySchema).
		WithIndex("products").
		WithDetails(map[string]interface{}{"key": "value"}).
		WithRecommendation("Fix it").
		WithFixCommand("curl ...")

	if f.IndexUID != "products" {
		t.Error("Chained WithIndex failed")
	}
	if f.Details["key"] != "value" {
		t.Error("Chained WithDetails failed")
	}
	if f.Recommendation != "Fix it" {
		t.Error("Chained WithRecommendation failed")
	}
	if f.FixCommand != "curl ..." {
		t.Error("Chained WithFixCommand failed")
	}
}

func TestSeverity_Weight(t *testing.T) {
	tests := []struct {
		severity Severity
		expected int
	}{
		{SeverityCritical, 4},
		{SeverityWarning, 3},
		{SeveritySuggestion, 2},
		{SeverityInfo, 1},
		{Severity("unknown"), 0},
		{Severity(""), 0},
	}

	for _, tt := range tests {
		t.Run(string(tt.severity), func(t *testing.T) {
			result := tt.severity.Weight()
			if result != tt.expected {
				t.Errorf("Severity(%q).Weight() = %d, want %d", tt.severity, result, tt.expected)
			}
		})
	}
}

func TestSeverityConstants(t *testing.T) {
	// Ensure severity values are what we expect (for JSON serialization)
	if SeverityCritical != "critical" {
		t.Errorf("SeverityCritical = %q, want %q", SeverityCritical, "critical")
	}
	if SeverityWarning != "warning" {
		t.Errorf("SeverityWarning = %q, want %q", SeverityWarning, "warning")
	}
	if SeveritySuggestion != "suggestion" {
		t.Errorf("SeveritySuggestion = %q, want %q", SeveritySuggestion, "suggestion")
	}
	if SeverityInfo != "info" {
		t.Errorf("SeverityInfo = %q, want %q", SeverityInfo, "info")
	}
}

func TestCategoryConstants(t *testing.T) {
	// Ensure category values are what we expect (for JSON serialization)
	if CategorySchema != "schema" {
		t.Errorf("CategorySchema = %q, want %q", CategorySchema, "schema")
	}
	if CategoryDocument != "document" {
		t.Errorf("CategoryDocument = %q, want %q", CategoryDocument, "document")
	}
	if CategoryPerformance != "performance" {
		t.Errorf("CategoryPerformance = %q, want %q", CategoryPerformance, "performance")
	}
	if CategoryBestPractice != "best_practice" {
		t.Errorf("CategoryBestPractice = %q, want %q", CategoryBestPractice, "best_practice")
	}
	if CategoryInstance != "instance" {
		t.Errorf("CategoryInstance = %q, want %q", CategoryInstance, "instance")
	}
	if CategorySearchProbe != "search_probe" {
		t.Errorf("CategorySearchProbe = %q, want %q", CategorySearchProbe, "search_probe")
	}
}
