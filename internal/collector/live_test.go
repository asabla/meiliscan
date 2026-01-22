package collector

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestLiveCollector_Collect(t *testing.T) {
	// Create a mock Meilisearch server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		switch r.URL.Path {
		case "/version":
			json.NewEncoder(w).Encode(map[string]string{
				"pkgVersion": "1.16.0",
			})
		case "/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"databaseSize":     524288000,
				"usedDatabaseSize": 262144000,
			})
		case "/indexes":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{
						"uid":        "products",
						"primaryKey": "id",
						"createdAt":  "2026-01-01T00:00:00Z",
						"updatedAt":  "2026-01-15T00:00:00Z",
					},
				},
			})
		case "/indexes/products/settings":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"displayedAttributes":  []string{"*"},
				"searchableAttributes": []string{"title", "description"},
				"filterableAttributes": []string{"price", "category"},
				"sortableAttributes":   []string{"price", "created_at"},
				"rankingRules": []string{
					"words", "typo", "proximity", "attribute", "sort", "exactness",
				},
				"stopWords": []string{},
				"synonyms":  map[string][]string{},
			})
		case "/indexes/products/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"numberOfDocuments": 1000,
				"isIndexing":        false,
				"fieldDistribution": map[string]int64{
					"id":          1000,
					"title":       1000,
					"description": 950,
					"price":       1000,
				},
			})
		case "/indexes/products/documents":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{"id": 1, "title": "Product 1", "price": 9.99},
					{"id": 2, "title": "Product 2", "price": 19.99},
				},
			})
		case "/tasks":
			json.NewEncoder(w).Encode(map[string]interface{}{
				"results": []map[string]interface{}{
					{
						"uid":      1,
						"indexUid": "products",
						"status":   "succeeded",
						"type":     "documentAdditionOrUpdate",
					},
				},
			})
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	// Create collector pointing to mock server
	collector := NewLiveCollector(server.URL, "test-api-key")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	data, err := collector.Collect(ctx)
	if err != nil {
		t.Fatalf("Collect failed: %v", err)
	}

	// Verify collected data
	if data.Version != "1.16.0" {
		t.Errorf("Version = %q, want %q", data.Version, "1.16.0")
	}
	if data.SourceType != "live" {
		t.Errorf("SourceType = %q, want %q", data.SourceType, "live")
	}
	if data.SourceURL != server.URL {
		t.Errorf("SourceURL = %q, want %q", data.SourceURL, server.URL)
	}
	if data.Stats == nil {
		t.Fatal("Stats should not be nil")
	}
	if data.Stats.DatabaseSize != 524288000 {
		t.Errorf("Stats.DatabaseSize = %d, want 524288000", data.Stats.DatabaseSize)
	}
	if len(data.Indexes) != 1 {
		t.Fatalf("len(Indexes) = %d, want 1", len(data.Indexes))
	}
	if data.Indexes[0].UID != "products" {
		t.Errorf("Indexes[0].UID = %q, want %q", data.Indexes[0].UID, "products")
	}
	if data.Indexes[0].NumberOfDocuments != 1000 {
		t.Errorf("Indexes[0].NumberOfDocuments = %d, want 1000", data.Indexes[0].NumberOfDocuments)
	}
	if data.Indexes[0].Settings == nil {
		t.Fatal("Indexes[0].Settings should not be nil")
	}
	if len(data.Indexes[0].Settings.SearchableAttributes) != 2 {
		t.Errorf("len(SearchableAttributes) = %d, want 2", len(data.Indexes[0].Settings.SearchableAttributes))
	}
	if data.InstanceInfo == nil || !data.InstanceInfo.HasMasterKey {
		t.Error("InstanceInfo.HasMasterKey should be true when API key is provided")
	}
}

func TestLiveCollector_CollectWithoutAPIKey(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Check no Authorization header
		if auth := r.Header.Get("Authorization"); auth != "" {
			t.Errorf("Should not have Authorization header, got %q", auth)
		}

		w.Header().Set("Content-Type", "application/json")

		switch r.URL.Path {
		case "/version":
			json.NewEncoder(w).Encode(map[string]string{"pkgVersion": "1.16.0"})
		case "/stats":
			json.NewEncoder(w).Encode(map[string]interface{}{"databaseSize": 0})
		case "/indexes":
			json.NewEncoder(w).Encode(map[string]interface{}{"results": []interface{}{}})
		case "/tasks":
			json.NewEncoder(w).Encode(map[string]interface{}{"results": []interface{}{}})
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "") // No API key

	ctx := context.Background()
	data, err := collector.Collect(ctx)
	if err != nil {
		t.Fatalf("Collect failed: %v", err)
	}

	if data.InstanceInfo == nil || data.InstanceInfo.HasMasterKey {
		t.Error("InstanceInfo.HasMasterKey should be false when no API key is provided")
	}
}

func TestLiveCollector_CollectVersionError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/version" {
			http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
			return
		}
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx := context.Background()
	_, err := collector.Collect(ctx)
	if err == nil {
		t.Error("Expected error when version fails")
	}
	if err.Error() != "failed to get version: failed to get version: unexpected status 503" {
		t.Logf("Got error: %v", err)
	}
}

func TestLiveCollector_CollectStatsError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		switch r.URL.Path {
		case "/version":
			json.NewEncoder(w).Encode(map[string]string{"pkgVersion": "1.16.0"})
		case "/stats":
			http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		}
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx := context.Background()
	_, err := collector.Collect(ctx)
	if err == nil {
		t.Error("Expected error when stats fails")
	}
}

func TestLiveCollector_Search(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/indexes/products/search" {
			http.NotFound(w, r)
			return
		}
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// Verify request body
		var req SearchRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request", http.StatusBadRequest)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"hits": []map[string]interface{}{
				{"id": 1, "title": "Test Product"},
			},
			"query":              req.Query,
			"processingTimeMs":   5,
			"estimatedTotalHits": 1,
		})
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "test-key")

	ctx := context.Background()
	resp, err := collector.Search(ctx, "products", SearchRequest{
		Query: "test",
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(resp.Hits) != 1 {
		t.Errorf("len(Hits) = %d, want 1", len(resp.Hits))
	}
	if resp.Query != "test" {
		t.Errorf("Query = %q, want %q", resp.Query, "test")
	}
	if resp.ProcessingTimeMs != 5 {
		t.Errorf("ProcessingTimeMs = %d, want 5", resp.ProcessingTimeMs)
	}
	if len(resp.RawResponse) == 0 {
		t.Error("RawResponse should be populated")
	}
}

func TestLiveCollector_SearchWithSort(t *testing.T) {
	var receivedReq SearchRequest

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedReq)

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"hits":             []map[string]interface{}{},
			"query":            "",
			"processingTimeMs": 1,
		})
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx := context.Background()
	_, err := collector.Search(ctx, "products", SearchRequest{
		Query: "",
		Sort:  []string{"price:asc"},
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(receivedReq.Sort) != 1 || receivedReq.Sort[0] != "price:asc" {
		t.Errorf("Sort = %v, want [price:asc]", receivedReq.Sort)
	}
}

func TestLiveCollector_SearchWithFilter(t *testing.T) {
	var receivedReq SearchRequest

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewDecoder(r.Body).Decode(&receivedReq)

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"hits":             []map[string]interface{}{},
			"query":            "",
			"processingTimeMs": 1,
		})
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx := context.Background()
	_, err := collector.Search(ctx, "products", SearchRequest{
		Query:  "",
		Filter: "price > 10",
	})
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if receivedReq.Filter != "price > 10" {
		t.Errorf("Filter = %q, want %q", receivedReq.Filter, "price > 10")
	}
}

func TestLiveCollector_SearchError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"message": "Invalid filter",
			"code":    "invalid_filter",
		})
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx := context.Background()
	_, err := collector.Search(ctx, "products", SearchRequest{Filter: "invalid"})
	if err == nil {
		t.Error("Expected error on search failure")
	}
}

func TestLiveCollector_GetSampleDocuments(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/indexes/products/documents" {
			http.NotFound(w, r)
			return
		}

		// Check limit parameter
		limit := r.URL.Query().Get("limit")
		if limit != "5" {
			t.Errorf("limit = %q, want %q", limit, "5")
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"results": []map[string]interface{}{
				{"id": 1, "title": "Doc 1"},
				{"id": 2, "title": "Doc 2"},
				{"id": 3, "title": "Doc 3"},
			},
		})
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx := context.Background()
	docs, err := collector.GetSampleDocuments(ctx, "products", 5)
	if err != nil {
		t.Fatalf("GetSampleDocuments failed: %v", err)
	}

	if len(docs) != 3 {
		t.Errorf("len(docs) = %d, want 3", len(docs))
	}
}

func TestLiveCollector_ConnectionTimeout(t *testing.T) {
	// Create a collector pointing to non-existent address
	collector := NewLiveCollector("http://localhost:59999", "")

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	_, err := collector.Collect(ctx)
	if err == nil {
		t.Error("Expected error on connection failure")
	}
}

func TestLiveCollector_ContextCancellation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Simulate slow response
		time.Sleep(500 * time.Millisecond)
		json.NewEncoder(w).Encode(map[string]string{"pkgVersion": "1.16.0"})
	}))
	defer server.Close()

	collector := NewLiveCollector(server.URL, "")

	ctx, cancel := context.WithCancel(context.Background())
	// Cancel immediately
	cancel()

	_, err := collector.Collect(ctx)
	if err == nil {
		t.Error("Expected error on context cancellation")
	}
}
