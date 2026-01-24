package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

// Web UI E2E Tests
// These tests verify complete user flows through the web interface.

// TestE2E_DashboardFlow tests the complete dashboard experience
func TestE2E_DashboardFlow(t *testing.T) {
	// Create mock Meilisearch server
	mockMeili := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/version":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"pkgVersion": "1.12.0",
			})
		case "/indexes":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"uid": "movies", "primaryKey": "id"},
					{"uid": "products", "primaryKey": "sku"},
				},
				"total": 2,
			})
		case "/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"databaseSize": 5242880,
			})
		case "/indexes/movies/stats", "/indexes/products/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"numberOfDocuments": 500,
				"isIndexing":        false,
			})
		case "/indexes/movies/settings", "/indexes/products/settings":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"searchableAttributes": []string{"*"},
				"filterableAttributes": []string{},
				"sortableAttributes":   []string{},
				"rankingRules":         []string{"words", "typo", "proximity"},
			})
		case "/indexes/movies/documents", "/indexes/products/documents":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"id": 1, "title": "Test"},
				},
			})
		case "/tasks":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{},
				"total":   0,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer mockMeili.Close()

	s := NewServer()

	// Step 1: Visit dashboard without session - should show connect form
	t.Run("dashboard_disconnected", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		body := w.Body.String()
		// Should contain connect form
		if !strings.Contains(body, "Connect") {
			t.Error("expected dashboard to show Connect option")
		}
	})

	// Step 2: Connect to Meilisearch
	t.Run("connect", func(t *testing.T) {
		form := url.Values{}
		form.Set("url", mockMeili.URL)
		form.Set("api_key", "")

		req := httptest.NewRequest("POST", "/connect", strings.NewReader(form.Encode()))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		// Should redirect to dashboard
		if w.Code != http.StatusSeeOther {
			t.Fatalf("expected 303 redirect, got %d", w.Code)
		}
		if w.Header().Get("Location") != "/" {
			t.Errorf("expected redirect to /, got %s", w.Header().Get("Location"))
		}
	})

	// Step 3: Dashboard should now show analysis results
	t.Run("dashboard_connected", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		body := w.Body.String()
		// Should contain index info
		if !strings.Contains(body, "movies") {
			t.Error("expected dashboard to show 'movies' index")
		}
		if !strings.Contains(body, "products") {
			t.Error("expected dashboard to show 'products' index")
		}
		// Should have health score
		if !strings.Contains(body, "Health") {
			t.Error("expected dashboard to show health score")
		}
	})

	// Step 4: Navigate to findings page
	t.Run("findings_page", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/findings", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		body := w.Body.String()
		// Should have filter controls
		if !strings.Contains(body, "filter") || !strings.Contains(body, "severity") {
			t.Error("expected findings page to have filter controls")
		}
	})

	// Step 5: Navigate to index detail
	t.Run("index_detail", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/index/movies", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		body := w.Body.String()
		if !strings.Contains(body, "movies") {
			t.Error("expected index detail to show index name")
		}
	})

	// Step 6: Disconnect
	t.Run("disconnect", func(t *testing.T) {
		req := httptest.NewRequest("POST", "/disconnect", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusSeeOther {
			t.Fatalf("expected 303 redirect, got %d", w.Code)
		}
	})

	// Step 7: Dashboard should be disconnected again
	t.Run("dashboard_after_disconnect", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		// Verify session is cleared
		s.mu.RLock()
		hasSession := s.currentReport != nil
		s.mu.RUnlock()

		if hasSession {
			t.Error("expected session to be cleared after disconnect")
		}
	})
}

// TestE2E_FindingsFilterFlow tests the findings filtering functionality
func TestE2E_FindingsFilterFlow(t *testing.T) {
	s := NewServer()

	// Setup session with varied findings
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		Indexes: []collector.IndexData{
			{UID: "movies", PrimaryKey: "id"},
			{UID: "products", PrimaryKey: "sku"},
		},
	}
	findings := []*finding.Finding{
		finding.New("S001", "Wildcard searchable", "Using wildcard", finding.SeverityCritical, finding.CategorySchema).WithIndex("movies"),
		finding.New("P001", "High failure rate", "Tasks failing", finding.SeverityCritical, finding.CategoryPerformance).WithIndex("movies"),
		finding.New("S004", "Empty filterable", "No filters", finding.SeverityInfo, finding.CategorySchema).WithIndex("products"),
		finding.New("D010", "PII detected", "Personal data", finding.SeverityCritical, finding.CategoryDocument).WithIndex("products"),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	// Test various filter combinations
	tests := []struct {
		name            string
		query           string
		expectedInBody  []string
		notExpectedBody []string
	}{
		{
			name:           "all findings",
			query:          "/findings/list",
			expectedInBody: []string{"S001", "P001", "S004", "D010"},
		},
		{
			name:            "filter by critical severity",
			query:           "/findings/list?severity=critical",
			expectedInBody:  []string{"S001", "P001", "D010"},
			notExpectedBody: []string{"S004"},
		},
		{
			name:            "filter by schema category",
			query:           "/findings/list?category=schema",
			expectedInBody:  []string{"S001", "S004"},
			notExpectedBody: []string{"P001", "D010"},
		},
		{
			name:            "filter by index",
			query:           "/findings/list?index=movies",
			expectedInBody:  []string{"S001", "P001"},
			notExpectedBody: []string{"S004", "D010"},
		},
		{
			name:            "combined filters",
			query:           "/findings/list?severity=critical&index=products",
			expectedInBody:  []string{"D010"},
			notExpectedBody: []string{"S001", "P001", "S004"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", tt.query, nil)
			w := httptest.NewRecorder()
			s.ServeHTTP(w, req)

			if w.Code != http.StatusOK {
				t.Fatalf("expected 200, got %d", w.Code)
			}

			body := w.Body.String()

			for _, expected := range tt.expectedInBody {
				if !strings.Contains(body, expected) {
					t.Errorf("expected body to contain %q", expected)
				}
			}

			for _, notExpected := range tt.notExpectedBody {
				if strings.Contains(body, notExpected) {
					t.Errorf("expected body NOT to contain %q", notExpected)
				}
			}
		})
	}
}

// TestE2E_ExportFlow tests the export functionality
func TestE2E_ExportFlow(t *testing.T) {
	s := NewServer()

	// Setup session
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		Indexes: []collector.IndexData{
			{UID: "test-index"},
		},
	}
	findings := []*finding.Finding{
		finding.New("TEST-001", "Test Finding", "Description", finding.SeverityWarning, finding.CategorySchema),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	// Test JSON export
	t.Run("json_export", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/api/export?format=json", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		// Should have attachment header
		cd := w.Header().Get("Content-Disposition")
		if !strings.Contains(cd, "attachment") {
			t.Errorf("expected attachment disposition, got %q", cd)
		}

		// Should be valid JSON report
		var exported report.Report
		if err := json.NewDecoder(w.Body).Decode(&exported); err != nil {
			t.Fatalf("failed to decode export: %v", err)
		}

		if len(exported.Findings) != 1 {
			t.Errorf("expected 1 finding in export, got %d", len(exported.Findings))
		}
	})
}

// TestE2E_APIAnalyzeFlow tests the API-based analysis flow
func TestE2E_APIAnalyzeFlow(t *testing.T) {
	// Create mock Meilisearch
	mockMeili := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/version":
			json.NewEncoder(w).Encode(map[string]interface{}{"pkgVersion": "1.12.0"})
		case "/indexes":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"uid": "test", "primaryKey": "id"},
				},
				"total": 1,
			})
		case "/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{"databaseSize": 1024})
		case "/indexes/test/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"numberOfDocuments": 10,
				"isIndexing":        false,
			})
		case "/indexes/test/settings":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"searchableAttributes": []string{"title"},
				"filterableAttributes": []string{"genre"},
			})
		case "/indexes/test/documents":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{},
			})
		case "/tasks":
			json.NewEncoder(w).Encode(map[string]interface{}{"results": []interface{}{}, "total": 0})
		default:
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]interface{}{})
		}
	}))
	defer mockMeili.Close()

	s := NewServer()

	// Step 1: Check health
	t.Run("health_check", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/api/health", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		var health HealthResponse
		json.NewDecoder(w.Body).Decode(&health)
		if health.Status != "ok" {
			t.Errorf("expected status ok, got %s", health.Status)
		}
	})

	// Step 2: Run analysis via API
	t.Run("api_analyze", func(t *testing.T) {
		reqBody, _ := json.Marshal(AnalyzeRequest{URL: mockMeili.URL})
		req := httptest.NewRequest("POST", "/api/analyze", strings.NewReader(string(reqBody)))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
		}

		var rpt report.Report
		if err := json.NewDecoder(w.Body).Decode(&rpt); err != nil {
			t.Fatalf("failed to decode report: %v", err)
		}

		if rpt.Instance.IndexCount != 1 {
			t.Errorf("expected 1 index, got %d", rpt.Instance.IndexCount)
		}
	})

	// Step 3: Export via API (should have data from previous analysis)
	t.Run("api_export", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/api/export", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}
	})
}

// TestE2E_ErrorHandling tests error scenarios in the web flow
func TestE2E_ErrorHandling(t *testing.T) {
	s := NewServer()

	// Test connection to invalid URL
	t.Run("connect_invalid_url", func(t *testing.T) {
		form := url.Values{}
		form.Set("url", "http://invalid-host-that-does-not-exist:9999")

		req := httptest.NewRequest("POST", "/connect", strings.NewReader(form.Encode()))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		// Should redirect with error
		if w.Code != http.StatusSeeOther {
			t.Fatalf("expected 303, got %d", w.Code)
		}

		location := w.Header().Get("Location")
		if !strings.Contains(location, "error=") {
			t.Errorf("expected error in redirect, got %s", location)
		}
	})

	// Test findings page without session
	t.Run("findings_no_session", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/findings", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		// Should redirect to dashboard
		if w.Code != http.StatusSeeOther {
			t.Fatalf("expected 303 redirect, got %d", w.Code)
		}
	})

	// Test index detail for non-existent index
	t.Run("index_not_found", func(t *testing.T) {
		// Setup minimal session
		data := &collector.CollectedData{
			Indexes: []collector.IndexData{{UID: "existing"}},
		}
		s.setSession(report.New(data, nil), data, "http://test")

		req := httptest.NewRequest("GET", "/index/nonexistent", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		// Should render not found page (200 with error content)
		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}

		body := w.Body.String()
		if !strings.Contains(body, "not found") && !strings.Contains(body, "Not Found") {
			t.Error("expected 'not found' message in body")
		}
	})

	// Test export with invalid format
	t.Run("export_invalid_format", func(t *testing.T) {
		data := &collector.CollectedData{}
		s.setSession(report.New(data, nil), data, "http://test")

		req := httptest.NewRequest("GET", "/api/export?format=xlsx", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		if w.Code != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", w.Code)
		}
	})
}

// TestE2E_PageContent verifies essential content is rendered on each page
func TestE2E_PageContent(t *testing.T) {
	s := NewServer()

	// Setup rich session data
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		Indexes: []collector.IndexData{
			{
				UID:               "movies",
				PrimaryKey:        "id",
				NumberOfDocuments: 15000,
			},
		},
		Stats: &collector.Stats{
			DatabaseSize: 52428800, // 50MB
		},
	}
	findings := []*finding.Finding{
		finding.New("S001", "Wildcard searchableAttributes", "Using wildcard * is inefficient", finding.SeverityCritical, finding.CategorySchema).WithIndex("movies"),
		finding.New("P003", "Database fragmentation", "Consider compacting", finding.SeveritySuggestion, finding.CategoryPerformance),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	// Dashboard content checks
	t.Run("dashboard_content", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		body := w.Body.String()

		checks := []string{
			"movies",         // Index name
			"Health",         // Health section
			"localhost:7700", // Source URL
		}

		for _, check := range checks {
			if !strings.Contains(body, check) {
				t.Errorf("dashboard missing expected content: %q", check)
			}
		}
	})

	// Findings page content checks (main page structure)
	t.Run("findings_page_structure", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/findings", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		body := w.Body.String()

		// The main page should have the filter structure
		checks := []string{
			"Critical",      // Severity count button
			"severity",      // Filter option
			"findings-list", // Container for HTMX content
		}

		for _, check := range checks {
			if !strings.Contains(body, check) {
				t.Errorf("findings page missing expected content: %q", check)
			}
		}
	})

	// Findings list (HTMX partial) content checks - this is what renders actual findings
	t.Run("findings_list_content", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/findings/list", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		body := w.Body.String()

		checks := []string{
			"S001",     // Finding ID
			"Wildcard", // Finding title content
			"critical", // Severity (lowercase in badge)
		}

		for _, check := range checks {
			if !strings.Contains(body, check) {
				t.Errorf("findings list missing expected content: %q", check)
			}
		}
	})

	// Index detail content checks
	t.Run("index_detail_content", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/index/movies", nil)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, req)

		body := w.Body.String()

		checks := []string{
			"movies", // Index name
			"id",     // Primary key
			"S001",   // Finding for this index
		}

		for _, check := range checks {
			if !strings.Contains(body, check) {
				t.Errorf("index detail missing expected content: %q", check)
			}
		}
	})
}
