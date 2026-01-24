// Package api provides the HTTP API server for Meiliscan.
package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/asabla/meiliscan/internal/analyzer"
	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
	"github.com/asabla/meiliscan/web/templates"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
)

const Version = "1.0.0"

// Server represents the API server.
type Server struct {
	router    chi.Router
	startTime time.Time

	// Session state for analysis results
	mu            sync.RWMutex
	currentReport *report.Report
	currentData   *collector.CollectedData
	sourceURL     string
}

// NewServer creates a new API server.
func NewServer() *Server {
	s := &Server{
		startTime: time.Now(),
	}
	s.setupRouter()
	return s
}

// setupRouter configures the Chi router with middleware and routes.
func (s *Server) setupRouter() {
	r := chi.NewRouter()

	// Middleware
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(10 * time.Minute))

	// CORS
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type"},
		ExposedHeaders:   []string{"Link"},
		AllowCredentials: false,
		MaxAge:           300,
	}))

	// Static files - served from web/static
	r.Handle("/static/*", http.StripPrefix("/static/", http.FileServer(http.Dir("web/static"))))

	// API Routes
	r.Route("/api", func(r chi.Router) {
		r.Get("/health", s.handleHealth)
		r.Post("/analyze", s.handleAnalyze)
		r.Post("/analyze/stream", s.handleAnalyzeStream)
		r.Get("/export", s.handleExport)
	})

	// Web Routes (HTML pages)
	r.Get("/", s.handleDashboard)
	r.Post("/connect", s.handleConnect)
	r.Post("/disconnect", s.handleDisconnect)
	r.Get("/findings", s.handleFindings)
	r.Get("/findings/list", s.handleFindingsList)
	r.Get("/index/{uid}", s.handleIndexDetail)

	s.router = r
}

// ServeHTTP implements http.Handler.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.router.ServeHTTP(w, r)
}

// ListenAndServe starts the HTTP server.
func (s *Server) ListenAndServe(addr string) error {
	log.Printf("Starting Meiliscan server on %s", addr)
	log.Printf("  Dashboard: http://localhost%s", addr)
	log.Printf("  API: http://localhost%s/api/health", addr)
	return http.ListenAndServe(addr, s)
}

// HealthResponse is the response for /api/health.
type HealthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
	Uptime  string `json:"uptime"`
}

// handleHealth handles GET /api/health.
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	uptime := time.Since(s.startTime).Round(time.Second)

	resp := HealthResponse{
		Status:  "ok",
		Version: Version,
		Uptime:  uptime.String(),
	}

	writeJSON(w, http.StatusOK, resp)
}

// AnalyzeRequest is the request body for /api/analyze.
type AnalyzeRequest struct {
	URL    string `json:"url"`
	APIKey string `json:"api_key,omitempty"`
}

// ErrorResponse is a standard error response.
type ErrorResponse struct {
	Error   string                 `json:"error"`
	Message string                 `json:"message"`
	Details map[string]interface{} `json:"details,omitempty"`
}

// handleAnalyze handles POST /api/analyze.
func (s *Server) handleAnalyze(w http.ResponseWriter, r *http.Request) {
	var req AnalyzeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", "Invalid JSON body")
		return
	}

	if req.URL == "" {
		writeError(w, http.StatusBadRequest, "invalid_request", "URL is required")
		return
	}

	// Create collector and run analysis
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	coll := collector.NewLiveCollector(req.URL, req.APIKey)

	data, err := coll.Collect(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "collection_failed",
			fmt.Sprintf("Failed to collect data: %v", err))
		return
	}

	// Run analyzers
	registry := analyzer.NewRegistry()
	findings := registry.Analyze(data)

	// Build report
	rpt := report.New(data, findings)

	// Store in session
	s.setSession(rpt, data, req.URL)

	// Return report as JSON
	writeJSON(w, http.StatusOK, rpt)
}

// ProgressEvent is sent during SSE streaming.
type ProgressEvent struct {
	Type     string      `json:"type"` // progress, complete, error
	Message  string      `json:"message"`
	Progress int         `json:"progress,omitempty"`
	Data     interface{} `json:"data,omitempty"`
}

// handleAnalyzeStream handles POST /api/analyze/stream with SSE.
func (s *Server) handleAnalyzeStream(w http.ResponseWriter, r *http.Request) {
	var req AnalyzeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", "Invalid JSON body")
		return
	}

	if req.URL == "" {
		writeError(w, http.StatusBadRequest, "invalid_request", "URL is required")
		return
	}

	// Set SSE headers
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no") // Disable nginx buffering

	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming_not_supported",
			"Streaming not supported")
		return
	}

	// Send progress events
	sendSSE := func(event ProgressEvent) {
		data, _ := json.Marshal(event)
		fmt.Fprintf(w, "data: %s\n\n", data)
		flusher.Flush()
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	// Progress: Connecting
	sendSSE(ProgressEvent{
		Type:     "progress",
		Message:  fmt.Sprintf("Connecting to %s...", req.URL),
		Progress: 10,
	})

	coll := collector.NewLiveCollector(req.URL, req.APIKey)

	// Progress: Collecting
	sendSSE(ProgressEvent{
		Type:     "progress",
		Message:  "Collecting data...",
		Progress: 30,
	})

	data, err := coll.Collect(ctx)
	if err != nil {
		sendSSE(ProgressEvent{
			Type:    "error",
			Message: fmt.Sprintf("Failed to collect data: %v", err),
		})
		return
	}

	// Progress: Analyzing
	sendSSE(ProgressEvent{
		Type:     "progress",
		Message:  fmt.Sprintf("Analyzing %d indexes...", len(data.Indexes)),
		Progress: 60,
	})

	registry := analyzer.NewRegistry()
	findings := registry.Analyze(data)

	// Progress: Building report
	sendSSE(ProgressEvent{
		Type:     "progress",
		Message:  "Building report...",
		Progress: 90,
	})

	rpt := report.New(data, findings)

	// Store in session
	s.setSession(rpt, data, req.URL)

	// Complete
	sendSSE(ProgressEvent{
		Type:     "complete",
		Message:  "Analysis complete",
		Progress: 100,
		Data:     rpt,
	})
}

// handleExport handles GET /api/export
func (s *Server) handleExport(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	rpt := s.currentReport
	s.mu.RUnlock()

	if rpt == nil {
		writeError(w, http.StatusNotFound, "no_report", "No analysis report available")
		return
	}

	format := r.URL.Query().Get("format")
	if format == "" {
		format = "json"
	}

	switch format {
	case "json":
		w.Header().Set("Content-Disposition", "attachment; filename=meiliscan-report.json")
		writeJSON(w, http.StatusOK, rpt)
	default:
		writeError(w, http.StatusBadRequest, "invalid_format", "Unsupported format. Use: json")
	}
}

// handleDashboard renders the dashboard page
func (s *Server) handleDashboard(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	rpt := s.currentReport
	data := s.currentData
	sourceURL := s.sourceURL
	s.mu.RUnlock()

	dashData := templates.DashboardData{
		IsConnected: rpt != nil,
		SourceURL:   sourceURL,
	}

	if rpt != nil && data != nil {
		dashData.Report = rpt
		dashData.Indexes = data.Indexes
		// Get top 5 findings
		if len(rpt.Findings) > 5 {
			dashData.TopFindings = rpt.Findings[:5]
		} else {
			dashData.TopFindings = rpt.Findings
		}
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := templates.Dashboard(dashData).Render(r.Context(), w); err != nil {
		log.Printf("Error rendering dashboard: %v", err)
		http.Error(w, "Error rendering page", http.StatusInternalServerError)
	}
}

// handleConnect handles form submission to connect to a Meilisearch instance
func (s *Server) handleConnect(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Redirect(w, r, "/?error=invalid_form", http.StatusSeeOther)
		return
	}

	url := r.FormValue("url")
	apiKey := r.FormValue("api_key")

	if url == "" {
		http.Redirect(w, r, "/?error=url_required", http.StatusSeeOther)
		return
	}

	// Run analysis
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	coll := collector.NewLiveCollector(url, apiKey)
	data, err := coll.Collect(ctx)
	if err != nil {
		log.Printf("Failed to collect data: %v", err)
		http.Redirect(w, r, "/?error=connection_failed", http.StatusSeeOther)
		return
	}

	registry := analyzer.NewRegistry()
	findings := registry.Analyze(data)
	rpt := report.New(data, findings)

	// Store in session
	s.setSession(rpt, data, url)

	// Redirect to dashboard
	http.Redirect(w, r, "/", http.StatusSeeOther)
}

// handleDisconnect clears the session
func (s *Server) handleDisconnect(w http.ResponseWriter, r *http.Request) {
	s.clearSession()
	http.Redirect(w, r, "/", http.StatusSeeOther)
}

// handleFindings renders the findings page
func (s *Server) handleFindings(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	rpt := s.currentReport
	data := s.currentData
	s.mu.RUnlock()

	if rpt == nil {
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}

	// Count by severity
	severityCounts := templates.SeverityCounts{
		Critical:   rpt.Summary.CriticalCount,
		Warning:    rpt.Summary.WarningCount,
		Suggestion: rpt.Summary.SuggestionCount,
		Info:       rpt.Summary.InfoCount,
	}

	// Get unique categories
	categorySet := make(map[string]bool)
	for _, f := range rpt.Findings {
		categorySet[string(f.Category)] = true
	}
	var categories []string
	for cat := range categorySet {
		categories = append(categories, cat)
	}

	// Get unique indexes
	var indexes []string
	if data != nil {
		for _, idx := range data.Indexes {
			indexes = append(indexes, idx.UID)
		}
	}

	findingsData := templates.FindingsData{
		Findings:        rpt.Findings,
		SeverityCounts:  severityCounts,
		Categories:      categories,
		Indexes:         indexes,
		CurrentSeverity: r.URL.Query().Get("severity"),
		CurrentCategory: r.URL.Query().Get("category"),
		CurrentIndex:    r.URL.Query().Get("index"),
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := templates.Findings(findingsData).Render(r.Context(), w); err != nil {
		log.Printf("Error rendering findings: %v", err)
		http.Error(w, "Error rendering page", http.StatusInternalServerError)
	}
}

// handleFindingsList renders just the findings list (for HTMX partial updates)
func (s *Server) handleFindingsList(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	rpt := s.currentReport
	s.mu.RUnlock()

	if rpt == nil {
		http.Error(w, "No report", http.StatusNotFound)
		return
	}

	// Filter findings based on query params
	severity := r.URL.Query().Get("severity")
	category := r.URL.Query().Get("category")
	index := r.URL.Query().Get("index")

	filtered := filterFindings(rpt.Findings, severity, category, index)

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := templates.FindingsList(filtered, severity, category, index).Render(r.Context(), w); err != nil {
		log.Printf("Error rendering findings list: %v", err)
		http.Error(w, "Error rendering page", http.StatusInternalServerError)
	}
}

// handleIndexDetail renders the index detail page
func (s *Server) handleIndexDetail(w http.ResponseWriter, r *http.Request) {
	uid := chi.URLParam(r, "uid")

	s.mu.RLock()
	rpt := s.currentReport
	data := s.currentData
	s.mu.RUnlock()

	if rpt == nil || data == nil {
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}

	// Find the index
	var indexData *collector.IndexData
	for i := range data.Indexes {
		if data.Indexes[i].UID == uid {
			indexData = &data.Indexes[i]
			break
		}
	}

	if indexData == nil {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		templates.IndexNotFound(uid).Render(r.Context(), w)
		return
	}

	// Get findings for this index
	var indexFindings []*finding.Finding
	for _, f := range rpt.Findings {
		if f.IndexUID == uid {
			indexFindings = append(indexFindings, f)
		}
	}

	detailData := templates.IndexDetailData{
		Index:    *indexData,
		Findings: indexFindings,
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := templates.IndexDetail(detailData).Render(r.Context(), w); err != nil {
		log.Printf("Error rendering index detail: %v", err)
		http.Error(w, "Error rendering page", http.StatusInternalServerError)
	}
}

// Session management helpers

func (s *Server) setSession(rpt *report.Report, data *collector.CollectedData, url string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.currentReport = rpt
	s.currentData = data
	s.sourceURL = url
}

func (s *Server) clearSession() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.currentReport = nil
	s.currentData = nil
	s.sourceURL = ""
}

// Helper functions

func filterFindings(findings []*finding.Finding, severity, category, index string) []*finding.Finding {
	var result []*finding.Finding
	for _, f := range findings {
		if severity != "" && string(f.Severity) != severity {
			continue
		}
		if category != "" && string(f.Category) != category {
			continue
		}
		if index != "" && f.IndexUID != index {
			continue
		}
		result = append(result, f)
	}
	return result
}

// writeJSON writes a JSON response.
func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

// writeError writes an error response.
func writeError(w http.ResponseWriter, status int, errorCode, message string) {
	writeJSON(w, status, ErrorResponse{
		Error:   errorCode,
		Message: message,
	})
}
