package collector

import (
	"archive/tar"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// DumpCollector collects data from a Meilisearch dump file.
// Meilisearch dumps are tar.gz archives with the following structure:
//
//	dump-{timestamp}/
//	├── metadata.json           # Version, dump date, instance UID
//	├── keys.json              # API keys (if present)
//	├── tasks/
//	│   └── queue.json         # Task history
//	└── indexes/
//	    └── {index_uid}/
//	        ├── metadata.json  # Index metadata, primary key
//	        ├── settings.json  # Complete index settings
//	        └── documents.jsonl # All documents (NDJSON format)
type DumpCollector struct {
	dumpPath      string
	maxSampleDocs int
}

// NewDumpCollector creates a new DumpCollector.
func NewDumpCollector(dumpPath string, maxSampleDocs int) *DumpCollector {
	if maxSampleDocs <= 0 {
		maxSampleDocs = 100
	}
	return &DumpCollector{
		dumpPath:      dumpPath,
		maxSampleDocs: maxSampleDocs,
	}
}

// Collect parses the dump file and returns collected data.
func (c *DumpCollector) Collect(ctx context.Context) (*CollectedData, error) {
	data := &CollectedData{
		SourceType:  "dump",
		SourceURL:   c.dumpPath,
		CollectedAt: time.Now(),
	}

	// Open the dump file
	file, err := os.Open(c.dumpPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open dump file: %w", err)
	}
	defer file.Close()

	// Create gzip reader
	gzr, err := gzip.NewReader(file)
	if err != nil {
		return nil, fmt.Errorf("failed to create gzip reader: %w", err)
	}
	defer gzr.Close()

	// Create tar reader
	tr := tar.NewReader(gzr)

	// We'll need to make multiple passes or store file contents
	// Since tar is sequential, we'll extract to memory selectively
	dumpFiles := make(map[string][]byte)
	var rootPrefix string

	// First pass: read all relevant files into memory
	for {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		default:
		}

		header, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("failed to read tar header: %w", err)
		}

		// Skip directories
		if header.Typeflag == tar.TypeDir {
			continue
		}

		// Determine root prefix from first file (dumps often have a root directory)
		if rootPrefix == "" {
			parts := strings.SplitN(header.Name, "/", 2)
			if len(parts) > 1 {
				// Check if first part looks like a dump root (e.g., "dump-20240101...")
				// but NOT if the first part is a known content directory
				firstPart := parts[0]
				if strings.HasPrefix(firstPart, "dump-") {
					rootPrefix = firstPart + "/"
				} else if firstPart != "indexes" && firstPart != "tasks" && firstPart != "keys" {
					// Unknown first part, might be a root directory - check if it looks like dump content
					if !strings.HasSuffix(parts[0], ".json") && !strings.HasSuffix(parts[0], ".jsonl") {
						// Could be a root directory, but only set if second part looks like dump content
						if parts[1] == "metadata.json" || strings.HasPrefix(parts[1], "indexes/") {
							rootPrefix = firstPart + "/"
						}
					}
				}
			}
		}

		// Normalize path by removing root prefix
		normalizedPath := header.Name
		if rootPrefix != "" && strings.HasPrefix(normalizedPath, rootPrefix) {
			normalizedPath = strings.TrimPrefix(normalizedPath, rootPrefix)
		}

		// Only read files we care about
		if shouldReadFile(normalizedPath) {
			content, err := io.ReadAll(tr)
			if err != nil {
				return nil, fmt.Errorf("failed to read %s: %w", header.Name, err)
			}
			dumpFiles[normalizedPath] = content
		}
	}

	// Parse dump metadata
	if content, ok := dumpFiles["metadata.json"]; ok {
		var metadata struct {
			DumpVersion string `json:"dumpVersion"`
			Version     string `json:"version"`
			DbVersion   string `json:"dbVersion"`
		}
		if err := json.Unmarshal(content, &metadata); err == nil {
			// Try different version fields
			if metadata.DumpVersion != "" {
				data.Version = metadata.DumpVersion
			} else if metadata.DbVersion != "" {
				data.Version = metadata.DbVersion
			} else if metadata.Version != "" {
				data.Version = metadata.Version
			}
		}
	}

	// Parse indexes
	indexUIDs := findIndexUIDs(dumpFiles)
	for _, uid := range indexUIDs {
		indexData, err := c.parseIndex(uid, dumpFiles)
		if err != nil {
			// Log warning but continue with other indexes
			continue
		}
		data.Indexes = append(data.Indexes, *indexData)
	}

	return data, nil
}

// shouldReadFile determines if a file should be read from the dump.
func shouldReadFile(path string) bool {
	// Always read top-level metadata
	if path == "metadata.json" {
		return true
	}

	// Read index metadata and settings
	if strings.HasPrefix(path, "indexes/") {
		base := filepath.Base(path)
		return base == "metadata.json" || base == "settings.json" || base == "documents.jsonl"
	}

	return false
}

// containsDumpContent checks if a path might contain dump content directly.
func containsDumpContent(name string) bool {
	return name == "indexes" || name == "metadata.json" || name == "tasks"
}

// findIndexUIDs extracts unique index UIDs from the dump files map.
func findIndexUIDs(files map[string][]byte) []string {
	uids := make(map[string]bool)
	for path := range files {
		if strings.HasPrefix(path, "indexes/") {
			parts := strings.Split(path, "/")
			if len(parts) >= 2 {
				uids[parts[1]] = true
			}
		}
	}

	result := make([]string, 0, len(uids))
	for uid := range uids {
		result = append(result, uid)
	}
	return result
}

// parseIndex parses an index from the dump files.
func (c *DumpCollector) parseIndex(uid string, files map[string][]byte) (*IndexData, error) {
	indexData := &IndexData{
		UID: uid,
	}

	// Parse index metadata
	metadataPath := fmt.Sprintf("indexes/%s/metadata.json", uid)
	if content, ok := files[metadataPath]; ok {
		var metadata struct {
			PrimaryKey string     `json:"primaryKey"`
			CreatedAt  *time.Time `json:"createdAt"`
			UpdatedAt  *time.Time `json:"updatedAt"`
		}
		if err := json.Unmarshal(content, &metadata); err == nil {
			indexData.PrimaryKey = metadata.PrimaryKey
			if metadata.CreatedAt != nil {
				indexData.CreatedAt = *metadata.CreatedAt
			}
			if metadata.UpdatedAt != nil {
				indexData.UpdatedAt = *metadata.UpdatedAt
			}
		}
	}

	// Parse settings
	settingsPath := fmt.Sprintf("indexes/%s/settings.json", uid)
	if content, ok := files[settingsPath]; ok {
		var settings IndexSettings
		if err := json.Unmarshal(content, &settings); err == nil {
			indexData.Settings = &settings
		}
	}

	// Parse documents (streaming to count and sample)
	documentsPath := fmt.Sprintf("indexes/%s/documents.jsonl", uid)
	if content, ok := files[documentsPath]; ok {
		docCount, sampleDocs, fieldDist := c.parseDocuments(content)
		indexData.NumberOfDocuments = docCount
		indexData.SampleDocuments = sampleDocs
		indexData.FieldDistribution = fieldDist
	}

	return indexData, nil
}

// parseDocuments parses a documents.jsonl file content.
// Returns document count, sample documents, and field distribution.
func (c *DumpCollector) parseDocuments(content []byte) (int64, []map[string]interface{}, map[string]int64) {
	var docCount int64
	sampleDocs := make([]map[string]interface{}, 0, c.maxSampleDocs)
	fieldDist := make(map[string]int64)

	// Process line by line
	start := 0
	for i := 0; i < len(content); i++ {
		if content[i] == '\n' || i == len(content)-1 {
			end := i
			if i == len(content)-1 && content[i] != '\n' {
				end = i + 1
			}

			line := content[start:end]
			start = i + 1

			if len(line) == 0 {
				continue
			}

			var doc map[string]interface{}
			if err := json.Unmarshal(line, &doc); err != nil {
				continue
			}

			docCount++

			// Track field distribution
			for field := range doc {
				fieldDist[field]++
			}

			// Collect sample documents
			if len(sampleDocs) < c.maxSampleDocs {
				sampleDocs = append(sampleDocs, doc)
			}
		}
	}

	return docCount, sampleDocs, fieldDist
}
