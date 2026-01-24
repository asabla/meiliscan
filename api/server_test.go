package api

import (
	"bytes"
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

func TestNewServer(t *testing.T) {
	s := NewServer()
	if s == nil {
		t.Fatal("expected server to be created")
	}
	if s.router == nil {
		t.Error("expected router to be initialized")
	}
	if s.startTime.IsZero() {
		t.Error("expected startTime to be set")
	}
}

func TestHealthEndpoint(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("GET", "/api/health", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var resp HealthResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.Status != "ok" {
		t.Errorf("expected status 'ok', got %q", resp.Status)
	}
	if resp.Version != Version {
		t.Errorf("expected version %q, got %q", Version, resp.Version)
	}
	if resp.Uptime == "" {
		t.Error("expected uptime to be set")
	}
}

func TestAnalyzeEndpoint_InvalidJSON(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("POST", "/api/analyze", strings.NewReader("not json"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}

	var resp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.Error != "invalid_request" {
		t.Errorf("expected error 'invalid_request', got %q", resp.Error)
	}
}

func TestAnalyzeEndpoint_MissingURL(t *testing.T) {
	s := NewServer()
	body := `{"api_key": "test"}`
	req := httptest.NewRequest("POST", "/api/analyze", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}

	var resp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.Error != "invalid_request" {
		t.Errorf("expected error 'invalid_request', got %q", resp.Error)
	}
	if !strings.Contains(resp.Message, "URL") {
		t.Errorf("expected message to mention URL, got %q", resp.Message)
	}
}

func TestExportEndpoint_NoReport(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("GET", "/api/export", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}

	var resp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.Error != "no_report" {
		t.Errorf("expected error 'no_report', got %q", resp.Error)
	}
}

func TestExportEndpoint_WithReport(t *testing.T) {
	s := NewServer()

	// Set up a mock report
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
	}
	findings := []*finding.Finding{
		finding.New("TEST-001", "Test Finding", "Description", finding.SeverityWarning, finding.CategoryPerformance),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	req := httptest.NewRequest("GET", "/api/export?format=json", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	// Check Content-Disposition header
	cd := w.Header().Get("Content-Disposition")
	if !strings.Contains(cd, "attachment") {
		t.Errorf("expected attachment content-disposition, got %q", cd)
	}

	// Decode as report
	var exportedReport report.Report
	if err := json.NewDecoder(w.Body).Decode(&exportedReport); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(exportedReport.Findings) != 1 {
		t.Errorf("expected 1 finding, got %d", len(exportedReport.Findings))
	}
}

func TestExportEndpoint_InvalidFormat(t *testing.T) {
	s := NewServer()

	// Set up a mock report
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
	}
	rpt := report.New(data, nil)
	s.setSession(rpt, data, "http://localhost:7700")

	req := httptest.NewRequest("GET", "/api/export?format=invalid", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestDashboardEndpoint_NoSession(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("GET", "/", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	// Check content type is HTML
	ct := w.Header().Get("Content-Type")
	if !strings.Contains(ct, "text/html") {
		t.Errorf("expected text/html content-type, got %q", ct)
	}
}

func TestDashboardEndpoint_WithSession(t *testing.T) {
	s := NewServer()

	// Set up a mock report
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		Indexes: []collector.IndexData{
			{UID: "movies", PrimaryKey: "id"},
		},
	}
	findings := []*finding.Finding{
		finding.New("TEST-001", "Finding 1", "Desc", finding.SeverityCritical, finding.CategoryPerformance),
		finding.New("TEST-002", "Finding 2", "Desc", finding.SeverityWarning, finding.CategoryPerformance),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	req := httptest.NewRequest("GET", "/", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}
}

func TestDisconnectEndpoint(t *testing.T) {
	s := NewServer()

	// Set up a mock session
	data := &collector.CollectedData{SourceType: "live"}
	rpt := report.New(data, nil)
	s.setSession(rpt, data, "http://localhost:7700")

	// Verify session exists
	s.mu.RLock()
	if s.currentReport == nil {
		t.Fatal("expected session to exist before disconnect")
	}
	s.mu.RUnlock()

	// Disconnect
	req := httptest.NewRequest("POST", "/disconnect", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	// Should redirect
	if w.Code != http.StatusSeeOther {
		t.Errorf("expected status 303 (SeeOther), got %d", w.Code)
	}

	// Session should be cleared
	s.mu.RLock()
	if s.currentReport != nil {
		t.Error("expected session to be cleared after disconnect")
	}
	s.mu.RUnlock()
}

func TestConnectEndpoint_MissingURL(t *testing.T) {
	s := NewServer()

	form := url.Values{}
	form.Set("api_key", "test-key")

	req := httptest.NewRequest("POST", "/connect", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	// Should redirect with error
	if w.Code != http.StatusSeeOther {
		t.Errorf("expected status 303, got %d", w.Code)
	}

	location := w.Header().Get("Location")
	if !strings.Contains(location, "error=url_required") {
		t.Errorf("expected redirect to include url_required error, got %q", location)
	}
}

func TestFindingsEndpoint_NoSession(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("GET", "/findings", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	// Should redirect to dashboard
	if w.Code != http.StatusSeeOther {
		t.Errorf("expected status 303, got %d", w.Code)
	}

	location := w.Header().Get("Location")
	if location != "/" {
		t.Errorf("expected redirect to /, got %q", location)
	}
}

func TestFindingsEndpoint_WithSession(t *testing.T) {
	s := NewServer()

	// Set up session
	data := &collector.CollectedData{
		SourceType: "live",
		SourceURL:  "http://localhost:7700",
		Indexes: []collector.IndexData{
			{UID: "movies"},
		},
	}
	findings := []*finding.Finding{
		finding.New("TEST-001", "Test", "Desc", finding.SeverityWarning, finding.CategoryPerformance).WithIndex("movies"),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	req := httptest.NewRequest("GET", "/findings", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}
}

func TestFindingsListEndpoint_NoSession(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("GET", "/findings/list", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}
}

func TestFindingsListEndpoint_WithFilters(t *testing.T) {
	s := NewServer()

	// Set up session with multiple findings
	data := &collector.CollectedData{SourceType: "live"}
	findings := []*finding.Finding{
		finding.New("TEST-001", "Critical", "Desc", finding.SeverityCritical, finding.CategoryPerformance).WithIndex("idx1"),
		finding.New("TEST-002", "Warning", "Desc", finding.SeverityWarning, finding.CategorySchema).WithIndex("idx2"),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	tests := []struct {
		name   string
		query  string
		status int
	}{
		{"no filter", "/findings/list", http.StatusOK},
		{"severity filter", "/findings/list?severity=critical", http.StatusOK},
		{"category filter", "/findings/list?category=performance", http.StatusOK},
		{"index filter", "/findings/list?index=idx1", http.StatusOK},
		{"combined filters", "/findings/list?severity=warning&category=schema", http.StatusOK},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", tt.query, nil)
			w := httptest.NewRecorder()

			s.ServeHTTP(w, req)

			if w.Code != tt.status {
				t.Errorf("expected status %d, got %d", tt.status, w.Code)
			}
		})
	}
}

func TestIndexDetailEndpoint_NoSession(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("GET", "/index/movies", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	// Should redirect to dashboard
	if w.Code != http.StatusSeeOther {
		t.Errorf("expected status 303, got %d", w.Code)
	}
}

func TestIndexDetailEndpoint_IndexNotFound(t *testing.T) {
	s := NewServer()

	// Set up session without the requested index
	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{UID: "other-index"},
		},
	}
	rpt := report.New(data, nil)
	s.setSession(rpt, data, "http://localhost:7700")

	req := httptest.NewRequest("GET", "/index/nonexistent", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	// Should render "not found" page (200 with error content)
	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}
}

func TestIndexDetailEndpoint_Success(t *testing.T) {
	s := NewServer()

	// Set up session with index
	data := &collector.CollectedData{
		SourceType: "live",
		Indexes: []collector.IndexData{
			{UID: "movies", PrimaryKey: "id", NumberOfDocuments: 1000},
		},
	}
	findings := []*finding.Finding{
		finding.New("TEST-001", "Test", "Desc", finding.SeverityWarning, finding.CategoryPerformance).WithIndex("movies"),
	}
	rpt := report.New(data, findings)
	s.setSession(rpt, data, "http://localhost:7700")

	req := httptest.NewRequest("GET", "/index/movies", nil)
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	ct := w.Header().Get("Content-Type")
	if !strings.Contains(ct, "text/html") {
		t.Errorf("expected text/html content-type, got %q", ct)
	}
}

func TestFilterFindings(t *testing.T) {
	findings := []*finding.Finding{
		finding.New("F1", "Critical Perf", "Desc", finding.SeverityCritical, finding.CategoryPerformance).WithIndex("idx1"),
		finding.New("F2", "Warning Schema", "Desc", finding.SeverityWarning, finding.CategorySchema).WithIndex("idx2"),
		finding.New("F3", "Info Perf", "Desc", finding.SeverityInfo, finding.CategoryPerformance).WithIndex("idx1"),
	}

	tests := []struct {
		name     string
		severity string
		category string
		index    string
		expected int
	}{
		{"no filter", "", "", "", 3},
		{"by severity", "critical", "", "", 1},
		{"by category", "", "performance", "", 2},
		{"by index", "", "", "idx1", 2},
		{"severity + category", "critical", "performance", "", 1},
		{"all filters", "info", "performance", "idx1", 1},
		{"no match", "critical", "schema", "idx1", 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := filterFindings(findings, tt.severity, tt.category, tt.index)
			if len(result) != tt.expected {
				t.Errorf("expected %d findings, got %d", tt.expected, len(result))
			}
		})
	}
}

func TestWriteJSON(t *testing.T) {
	w := httptest.NewRecorder()

	data := map[string]string{"key": "value"}
	writeJSON(w, http.StatusOK, data)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	ct := w.Header().Get("Content-Type")
	if ct != "application/json" {
		t.Errorf("expected application/json, got %q", ct)
	}

	var result map[string]string
	if err := json.NewDecoder(w.Body).Decode(&result); err != nil {
		t.Fatalf("failed to decode: %v", err)
	}

	if result["key"] != "value" {
		t.Errorf("expected value 'value', got %q", result["key"])
	}
}

func TestWriteError(t *testing.T) {
	w := httptest.NewRecorder()

	writeError(w, http.StatusBadRequest, "test_error", "Test message")

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}

	var resp ErrorResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode: %v", err)
	}

	if resp.Error != "test_error" {
		t.Errorf("expected error 'test_error', got %q", resp.Error)
	}
	if resp.Message != "Test message" {
		t.Errorf("expected message 'Test message', got %q", resp.Message)
	}
}

func TestAnalyzeStreamEndpoint_InvalidJSON(t *testing.T) {
	s := NewServer()
	req := httptest.NewRequest("POST", "/api/analyze/stream", strings.NewReader("not json"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestAnalyzeStreamEndpoint_MissingURL(t *testing.T) {
	s := NewServer()
	body := `{"api_key": "test"}`
	req := httptest.NewRequest("POST", "/api/analyze/stream", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestSessionManagement(t *testing.T) {
	s := NewServer()

	// Initially no session
	s.mu.RLock()
	if s.currentReport != nil {
		t.Error("expected no report initially")
	}
	s.mu.RUnlock()

	// Set session
	data := &collector.CollectedData{SourceType: "test"}
	rpt := report.New(data, nil)
	s.setSession(rpt, data, "http://test.local")

	// Verify session set
	s.mu.RLock()
	if s.currentReport == nil {
		t.Error("expected report after setSession")
	}
	if s.sourceURL != "http://test.local" {
		t.Errorf("expected sourceURL 'http://test.local', got %q", s.sourceURL)
	}
	s.mu.RUnlock()

	// Clear session
	s.clearSession()

	// Verify session cleared
	s.mu.RLock()
	if s.currentReport != nil {
		t.Error("expected no report after clearSession")
	}
	if s.sourceURL != "" {
		t.Error("expected empty sourceURL after clearSession")
	}
	s.mu.RUnlock()
}

// TestAnalyzeWithMockServer tests the analyze endpoint with a mock Meilisearch server
func TestAnalyzeEndpoint_WithMockMeilisearch(t *testing.T) {
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
				},
				"offset": 0,
				"limit":  20,
				"total":  1,
			})
		case "/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"databaseSize": 1024000,
			})
		case "/indexes/movies/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"numberOfDocuments": 100,
				"isIndexing":        false,
			})
		case "/indexes/movies/settings":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"searchableAttributes": []string{"*"},
				"filterableAttributes": []string{},
				"sortableAttributes":   []string{},
				"rankingRules":         []string{"words", "typo", "proximity"},
			})
		case "/indexes/movies/documents":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"id": 1, "title": "Test Movie"},
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

	// Create Meiliscan server
	s := NewServer()

	// Make analyze request
	reqBody := AnalyzeRequest{URL: mockMeili.URL}
	body, _ := json.Marshal(reqBody)
	req := httptest.NewRequest("POST", "/api/analyze", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	// Decode response
	var rpt report.Report
	if err := json.NewDecoder(w.Body).Decode(&rpt); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	// Verify report
	if rpt.Instance.IndexCount != 1 {
		t.Errorf("expected 1 index, got %d", rpt.Instance.IndexCount)
	}
}
