package collector

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"os"
	"testing"
)

func TestDumpCollector_Collect(t *testing.T) {
	// Create a test dump file
	dumpPath := createTestDump(t)
	defer os.Remove(dumpPath)

	collector := NewDumpCollector(dumpPath, 10)
	data, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("failed to collect: %v", err)
	}

	// Verify metadata
	if data.Version != "V6" {
		t.Errorf("expected version V6, got %s", data.Version)
	}

	if data.SourceType != "dump" {
		t.Errorf("expected source type dump, got %s", data.SourceType)
	}

	// Verify indexes
	if len(data.Indexes) != 1 {
		t.Fatalf("expected 1 index, got %d", len(data.Indexes))
	}

	idx := data.Indexes[0]
	if idx.UID != "products" {
		t.Errorf("expected index UID products, got %s", idx.UID)
	}

	if idx.PrimaryKey != "id" {
		t.Errorf("expected primary key id, got %s", idx.PrimaryKey)
	}

	if idx.NumberOfDocuments != 3 {
		t.Errorf("expected 3 documents, got %d", idx.NumberOfDocuments)
	}

	// Verify settings
	if idx.Settings == nil {
		t.Fatal("expected settings to be present")
	}

	if len(idx.Settings.SearchableAttributes) != 1 || idx.Settings.SearchableAttributes[0] != "*" {
		t.Errorf("expected wildcard searchable attributes, got %v", idx.Settings.SearchableAttributes)
	}

	// Verify sample documents
	if len(idx.SampleDocuments) != 3 {
		t.Errorf("expected 3 sample documents, got %d", len(idx.SampleDocuments))
	}

	// Verify field distribution
	if idx.FieldDistribution["id"] != 3 {
		t.Errorf("expected field 'id' count 3, got %d", idx.FieldDistribution["id"])
	}
}

func TestDumpCollector_FileNotFound(t *testing.T) {
	collector := NewDumpCollector("/nonexistent/dump.dump", 10)
	_, err := collector.Collect(context.Background())
	if err == nil {
		t.Error("expected error for nonexistent file")
	}
}

func TestDumpCollector_MaxSampleDocs(t *testing.T) {
	dumpPath := createTestDump(t)
	defer os.Remove(dumpPath)

	// Request only 2 sample docs
	collector := NewDumpCollector(dumpPath, 2)
	data, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("failed to collect: %v", err)
	}

	idx := data.Indexes[0]

	// Should have all 3 docs counted
	if idx.NumberOfDocuments != 3 {
		t.Errorf("expected 3 documents counted, got %d", idx.NumberOfDocuments)
	}

	// But only 2 samples
	if len(idx.SampleDocuments) != 2 {
		t.Errorf("expected 2 sample documents, got %d", len(idx.SampleDocuments))
	}
}

// createTestDump creates a minimal test dump file and returns its path.
func createTestDump(t *testing.T) string {
	t.Helper()

	tmpFile, err := os.CreateTemp("", "test-dump-*.dump")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	tmpFile.Close()

	// Create gzip writer
	file, err := os.Create(tmpFile.Name())
	if err != nil {
		t.Fatalf("failed to open file: %v", err)
	}
	defer file.Close()

	gzw := gzip.NewWriter(file)
	defer gzw.Close()

	tw := tar.NewWriter(gzw)
	defer tw.Close()

	// Add dump metadata
	addTarFile(t, tw, "metadata.json", `{"dumpVersion":"V6","dbVersion":"1.6.0"}`)

	// Add index metadata
	addTarFile(t, tw, "indexes/products/metadata.json", `{"primaryKey":"id","createdAt":"2024-01-01T00:00:00Z","updatedAt":"2024-01-01T00:00:00Z"}`)

	// Add index settings (wildcard searchable - should trigger S001)
	addTarFile(t, tw, "indexes/products/settings.json", `{
		"searchableAttributes": ["*"],
		"displayedAttributes": ["*"],
		"filterableAttributes": [],
		"sortableAttributes": [],
		"rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
		"stopWords": [],
		"synonyms": {}
	}`)

	// Add documents
	addTarFile(t, tw, "indexes/products/documents.jsonl", `{"id":1,"name":"Widget","price":9.99}
{"id":2,"name":"Gadget","price":19.99}
{"id":3,"name":"Gizmo","price":29.99}`)

	return tmpFile.Name()
}

func addTarFile(t *testing.T, tw *tar.Writer, name string, content string) {
	t.Helper()

	hdr := &tar.Header{
		Name: name,
		Mode: 0644,
		Size: int64(len(content)),
	}
	if err := tw.WriteHeader(hdr); err != nil {
		t.Fatalf("failed to write tar header for %s: %v", name, err)
	}
	if _, err := tw.Write([]byte(content)); err != nil {
		t.Fatalf("failed to write tar content for %s: %v", name, err)
	}
}

func TestDumpCollector_WithRootDirectory(t *testing.T) {
	// Test dump files that have a root directory like "dump-20240101T120000Z/"
	tmpFile, err := os.CreateTemp("", "test-dump-root-*.dump")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	tmpFile.Close()
	defer os.Remove(tmpFile.Name())

	file, err := os.Create(tmpFile.Name())
	if err != nil {
		t.Fatalf("failed to open file: %v", err)
	}
	defer file.Close()

	gzw := gzip.NewWriter(file)
	tw := tar.NewWriter(gzw)

	// Add files with root directory prefix
	addTarFile(t, tw, "dump-20240101T120000Z/metadata.json", `{"dumpVersion":"V6"}`)
	addTarFile(t, tw, "dump-20240101T120000Z/indexes/test/metadata.json", `{"primaryKey":"id"}`)
	addTarFile(t, tw, "dump-20240101T120000Z/indexes/test/settings.json", `{"searchableAttributes":["title"]}`)
	addTarFile(t, tw, "dump-20240101T120000Z/indexes/test/documents.jsonl", `{"id":1,"title":"Test"}`)

	tw.Close()
	gzw.Close()

	collector := NewDumpCollector(tmpFile.Name(), 10)
	data, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("failed to collect: %v", err)
	}

	if data.Version != "V6" {
		t.Errorf("expected version V6, got %s", data.Version)
	}

	if len(data.Indexes) != 1 {
		t.Fatalf("expected 1 index, got %d", len(data.Indexes))
	}

	if data.Indexes[0].UID != "test" {
		t.Errorf("expected index UID test, got %s", data.Indexes[0].UID)
	}
}

// Test that parsing a dump file triggers the expected findings
func TestDumpCollector_Integration(t *testing.T) {
	dumpPath := createTestDump(t)
	defer os.Remove(dumpPath)

	collector := NewDumpCollector(dumpPath, 10)
	data, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("failed to collect: %v", err)
	}

	// The test dump has:
	// - Wildcard searchable attributes (should trigger S001)
	// - Empty filterable attributes (should trigger S004)
	// - Default ranking rules (should trigger S007)

	idx := data.Indexes[0]

	// Verify S001 condition (wildcard searchable)
	if len(idx.Settings.SearchableAttributes) != 1 || idx.Settings.SearchableAttributes[0] != "*" {
		t.Errorf("expected wildcard searchable for S001 test")
	}

	// Verify S004 condition (empty filterable)
	if len(idx.Settings.FilterableAttributes) != 0 {
		t.Errorf("expected empty filterable for S004 test")
	}

	// Verify S007 condition (default ranking rules)
	expectedRules := []string{"words", "typo", "proximity", "attribute", "sort", "exactness"}
	if len(idx.Settings.RankingRules) != len(expectedRules) {
		t.Errorf("expected default ranking rules for S007 test")
	}
}

func TestParseDocuments(t *testing.T) {
	collector := &DumpCollector{maxSampleDocs: 2}

	content := []byte(`{"id":1,"name":"A"}
{"id":2,"name":"B"}
{"id":3,"name":"C"}
{"id":4,"name":"D"}`)

	count, samples, fieldDist := collector.parseDocuments(content)

	if count != 4 {
		t.Errorf("expected count 4, got %d", count)
	}

	if len(samples) != 2 {
		t.Errorf("expected 2 samples, got %d", len(samples))
	}

	if fieldDist["id"] != 4 {
		t.Errorf("expected id count 4, got %d", fieldDist["id"])
	}

	if fieldDist["name"] != 4 {
		t.Errorf("expected name count 4, got %d", fieldDist["name"])
	}
}

func TestFindIndexUIDs(t *testing.T) {
	files := map[string][]byte{
		"indexes/products/settings.json":   []byte("{}"),
		"indexes/products/documents.jsonl": []byte(""),
		"indexes/users/settings.json":      []byte("{}"),
		"metadata.json":                    []byte("{}"),
	}

	uids := findIndexUIDs(files)

	if len(uids) != 2 {
		t.Errorf("expected 2 UIDs, got %d", len(uids))
	}

	// Check both UIDs are present (order may vary)
	foundProducts := false
	foundUsers := false
	for _, uid := range uids {
		if uid == "products" {
			foundProducts = true
		}
		if uid == "users" {
			foundUsers = true
		}
	}

	if !foundProducts || !foundUsers {
		t.Errorf("expected products and users UIDs, got %v", uids)
	}
}
