package analyzer

import (
	"fmt"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// PerformanceAnalyzer analyzes performance-related aspects.
type PerformanceAnalyzer struct{}

// NewPerformanceAnalyzer creates a new PerformanceAnalyzer.
func NewPerformanceAnalyzer() *PerformanceAnalyzer {
	return &PerformanceAnalyzer{}
}

// Name returns the analyzer name.
func (a *PerformanceAnalyzer) Name() string {
	return "performance"
}

// Analyze runs performance analysis on the collected data.
func (a *PerformanceAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	// P003: Database fragmentation
	if f := a.checkDatabaseFragmentation(data); f != nil {
		findings = append(findings, f)
	}

	// P004: Too many indexes
	if f := a.checkTooManyIndexes(data); f != nil {
		findings = append(findings, f)
	}

	// P005: Index imbalance
	if f := a.checkIndexImbalance(data); f != nil {
		findings = append(findings, f)
	}

	// P006: Too many fields per index
	for _, idx := range data.Indexes {
		if f := a.checkFieldCount(idx); f != nil {
			findings = append(findings, f)
		}
	}

	return findings
}

// P003: Database fragmentation
func (a *PerformanceAnalyzer) checkDatabaseFragmentation(data *collector.CollectedData) *finding.Finding {
	if data.Stats == nil {
		return nil
	}

	dbSize := data.Stats.DatabaseSize
	usedSize := data.Stats.UsedDatabaseSize

	if dbSize == 0 || usedSize == 0 {
		return nil
	}

	usageRatio := float64(usedSize) / float64(dbSize)

	// Less than 60% utilization suggests fragmentation
	if usageRatio < 0.6 {
		fragmentation := (1 - usageRatio) * 100
		return finding.New(
			"MEILI-P003",
			"Database fragmentation detected",
			fmt.Sprintf("Database is only %.0f%% utilized (%.0f%% fragmentation). Consider creating a dump and re-importing to reclaim space.", usageRatio*100, fragmentation),
			finding.SeveritySuggestion,
			finding.CategoryPerformance,
		).WithRecommendation("Create a dump using `meilisearch --dump-dir` and re-import to defragment the database.").
			WithDetails(map[string]interface{}{
				"database_size_bytes":      dbSize,
				"used_database_size_bytes": usedSize,
				"utilization_percent":      usageRatio * 100,
			})
	}

	return nil
}

// P004: Too many indexes
func (a *PerformanceAnalyzer) checkTooManyIndexes(data *collector.CollectedData) *finding.Finding {
	const threshold = 50

	if len(data.Indexes) >= threshold {
		f := finding.New(
			"MEILI-P004",
			"Too many indexes",
			fmt.Sprintf("Instance has %d indexes. Large numbers of indexes can impact memory usage and startup time.", len(data.Indexes)),
			finding.SeveritySuggestion,
			finding.CategoryPerformance,
		).WithRecommendation("Consider consolidating related data into fewer indexes using filterable attributes for segmentation.").
			WithDetails(map[string]interface{}{
				"index_count": len(data.Indexes),
				"threshold":   threshold,
			})

		return f
	}

	return nil
}

// P005: Index imbalance
func (a *PerformanceAnalyzer) checkIndexImbalance(data *collector.CollectedData) *finding.Finding {
	if len(data.Indexes) < 2 {
		return nil
	}

	var totalDocs int64
	for _, idx := range data.Indexes {
		totalDocs += idx.NumberOfDocuments
	}

	if totalDocs == 0 {
		return nil
	}

	// Find dominant index
	for _, idx := range data.Indexes {
		if idx.NumberOfDocuments > 0 {
			ratio := float64(idx.NumberOfDocuments) / float64(totalDocs)
			if ratio > 0.8 { // One index has >80% of documents
				return finding.New(
					"MEILI-P005",
					"Imbalanced index distribution",
					fmt.Sprintf("Index '%s' contains %.0f%% of all documents (%d of %d). This may be intentional, but verify data distribution.", idx.UID, ratio*100, idx.NumberOfDocuments, totalDocs),
					finding.SeverityInfo,
					finding.CategoryPerformance,
				).WithIndex(idx.UID).
					WithDetails(map[string]interface{}{
						"dominant_index":  idx.UID,
						"document_count":  idx.NumberOfDocuments,
						"total_documents": totalDocs,
						"percentage":      ratio * 100,
					})
			}
		}
	}

	return nil
}

// P006: Too many fields
func (a *PerformanceAnalyzer) checkFieldCount(idx collector.IndexData) *finding.Finding {
	fieldCount := len(idx.FieldDistribution)

	if fieldCount > 100 {
		return finding.New(
			"MEILI-P006",
			"Too many unique fields",
			fmt.Sprintf("Index '%s' has %d unique fields. Having more than 100 fields can impact indexing performance and memory usage.", idx.UID, fieldCount),
			finding.SeverityWarning,
			finding.CategoryPerformance,
		).WithIndex(idx.UID).
			WithRecommendation("Consider flattening document structure or removing unnecessary fields.").
			WithDetails(map[string]interface{}{
				"field_count": fieldCount,
				"threshold":   100,
			})
	}

	return nil
}
