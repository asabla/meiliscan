// Package api provides the HTTP API server for Meiliscan.
package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/asabla/meiliscan/internal/analyzer"
	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/report"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
)

const Version = "1.0.0"

// Server represents the API server.
type Server struct {
	router    chi.Router
	startTime time.Time
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

	// Routes
	r.Route("/api", func(r chi.Router) {
		r.Get("/health", s.handleHealth)
		r.Post("/analyze", s.handleAnalyze)
		r.Post("/analyze/stream", s.handleAnalyzeStream)
	})

	s.router = r
}

// ServeHTTP implements http.Handler.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.router.ServeHTTP(w, r)
}

// ListenAndServe starts the HTTP server.
func (s *Server) ListenAndServe(addr string) error {
	log.Printf("Starting Meiliscan API server on %s", addr)
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

	// Complete
	sendSSE(ProgressEvent{
		Type:     "complete",
		Message:  "Analysis complete",
		Progress: 100,
		Data:     rpt,
	})
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
