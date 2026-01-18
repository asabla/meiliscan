// Package collector provides data collection from Meilisearch sources.
package collector

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// CollectedData holds all data collected from a Meilisearch source.
type CollectedData struct {
	// Source information
	SourceType  string    `json:"source_type"` // "live" or "dump"
	SourceURL   string    `json:"source_url,omitempty"`
	CollectedAt time.Time `json:"collected_at"`

	// Instance information
	Version string `json:"version,omitempty"`

	// Stats
	Stats *Stats `json:"stats,omitempty"`

	// Indexes with their settings and sample documents
	Indexes []IndexData `json:"indexes"`
}

// Stats represents instance-level statistics.
type Stats struct {
	DatabaseSize     int64      `json:"databaseSize"`
	UsedDatabaseSize int64      `json:"usedDatabaseSize,omitempty"`
	LastUpdate       *time.Time `json:"lastUpdate,omitempty"`
}

// IndexData holds data for a single index.
type IndexData struct {
	UID               string                   `json:"uid"`
	PrimaryKey        string                   `json:"primaryKey,omitempty"`
	CreatedAt         time.Time                `json:"createdAt"`
	UpdatedAt         time.Time                `json:"updatedAt"`
	NumberOfDocuments int64                    `json:"numberOfDocuments"`
	IsIndexing        bool                     `json:"isIndexing"`
	Settings          *IndexSettings           `json:"settings"`
	SampleDocuments   []map[string]interface{} `json:"sampleDocuments,omitempty"`
	FieldDistribution map[string]int64         `json:"fieldDistribution,omitempty"`
}

// IndexSettings represents Meilisearch index settings.
type IndexSettings struct {
	DisplayedAttributes  []string            `json:"displayedAttributes"`
	SearchableAttributes []string            `json:"searchableAttributes"`
	FilterableAttributes []string            `json:"filterableAttributes"`
	SortableAttributes   []string            `json:"sortableAttributes"`
	RankingRules         []string            `json:"rankingRules"`
	StopWords            []string            `json:"stopWords"`
	Synonyms             map[string][]string `json:"synonyms"`
	DistinctAttribute    *string             `json:"distinctAttribute"`
	TypoTolerance        *TypoTolerance      `json:"typoTolerance"`
	Faceting             *Faceting           `json:"faceting"`
	Pagination           *Pagination         `json:"pagination"`
}

// TypoTolerance settings.
type TypoTolerance struct {
	Enabled             bool                `json:"enabled"`
	MinWordSizeForTypos MinWordSizeForTypos `json:"minWordSizeForTypos"`
	DisableOnWords      []string            `json:"disableOnWords"`
	DisableOnAttributes []string            `json:"disableOnAttributes"`
}

// MinWordSizeForTypos settings.
type MinWordSizeForTypos struct {
	OneTypo  int `json:"oneTypo"`
	TwoTypos int `json:"twoTypos"`
}

// Faceting settings.
type Faceting struct {
	MaxValuesPerFacet int `json:"maxValuesPerFacet"`
}

// Pagination settings.
type Pagination struct {
	MaxTotalHits int `json:"maxTotalHits"`
}

// Collector defines the interface for data collection.
type Collector interface {
	Collect(ctx context.Context) (*CollectedData, error)
}

// LiveCollector collects data from a live Meilisearch instance.
type LiveCollector struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// NewLiveCollector creates a new LiveCollector.
func NewLiveCollector(baseURL, apiKey string) *LiveCollector {
	return &LiveCollector{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// Collect fetches data from the Meilisearch instance.
func (c *LiveCollector) Collect(ctx context.Context) (*CollectedData, error) {
	data := &CollectedData{
		SourceType:  "live",
		SourceURL:   c.baseURL,
		CollectedAt: time.Now(),
	}

	// Get version
	version, err := c.getVersion(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get version: %w", err)
	}
	data.Version = version

	// Get stats
	stats, err := c.getStats(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get stats: %w", err)
	}
	data.Stats = stats

	// Get indexes
	indexes, err := c.getIndexes(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get indexes: %w", err)
	}

	// Fetch settings for each index
	for i := range indexes {
		settings, err := c.getIndexSettings(ctx, indexes[i].UID)
		if err != nil {
			return nil, fmt.Errorf("failed to get settings for index %s: %w", indexes[i].UID, err)
		}
		indexes[i].Settings = settings
	}

	data.Indexes = indexes

	return data, nil
}

func (c *LiveCollector) doRequest(ctx context.Context, method, path string, body io.Reader) (*http.Response, error) {
	url := c.baseURL + path
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, err
	}

	if c.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	}
	req.Header.Set("Content-Type", "application/json")

	return c.httpClient.Do(req)
}

func (c *LiveCollector) getVersion(ctx context.Context) (string, error) {
	resp, err := c.doRequest(ctx, "GET", "/version", nil)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var result struct {
		PkgVersion string `json:"pkgVersion"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}

	return result.PkgVersion, nil
}

func (c *LiveCollector) getStats(ctx context.Context) (*Stats, error) {
	resp, err := c.doRequest(ctx, "GET", "/stats", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var result Stats
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return &result, nil
}

func (c *LiveCollector) getIndexes(ctx context.Context) ([]IndexData, error) {
	resp, err := c.doRequest(ctx, "GET", "/indexes", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var result struct {
		Results []IndexData `json:"results"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return result.Results, nil
}

func (c *LiveCollector) getIndexSettings(ctx context.Context, uid string) (*IndexSettings, error) {
	resp, err := c.doRequest(ctx, "GET", "/indexes/"+uid+"/settings", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var result IndexSettings
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	return &result, nil
}
