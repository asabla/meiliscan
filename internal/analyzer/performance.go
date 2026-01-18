package analyzer

import (
	"fmt"
	"regexp"

	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// durationRegex parses ISO 8601 duration strings like "PT1.234S" or "PT1M30.5S"
var durationRegex = regexp.MustCompile(`PT(?:(\d+)M)?(\d+\.?\d*)S`)

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

	// P001: High task failure rate
	if f := a.checkTaskFailures(data); f != nil {
		findings = append(findings, f)
	}

	// P002: Slow indexing
	if f := a.checkSlowIndexing(data); f != nil {
		findings = append(findings, f)
	}

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

	// P007: Task queue backlog
	if f := a.checkTaskBacklog(data); f != nil {
		findings = append(findings, f)
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

// P001: High task failure rate
func (a *PerformanceAnalyzer) checkTaskFailures(data *collector.CollectedData) *finding.Finding {
	if len(data.Tasks) < 10 {
		return nil
	}

	var failedCount int
	for _, task := range data.Tasks {
		if task.Status == "failed" {
			failedCount++
		}
	}

	totalTasks := len(data.Tasks)
	failureRate := float64(failedCount) / float64(totalTasks)

	// P001: More than 10% failures
	if failureRate > 0.1 {
		return finding.New(
			"MEILI-P001",
			"High task failure rate",
			fmt.Sprintf("Task failure rate is %.1f%% (%d failed out of %d). Review failed tasks for recurring issues.", failureRate*100, failedCount, totalTasks),
			finding.SeverityCritical,
			finding.CategoryPerformance,
		).WithRecommendation("Check task error messages for common patterns. Common causes include malformed documents, missing primary keys, or resource constraints.").
			WithDetails(map[string]interface{}{
				"failed_tasks":     failedCount,
				"total_tasks":      totalTasks,
				"failure_rate_pct": failureRate * 100,
			})
	}

	return nil
}

// P002: Slow indexing
func (a *PerformanceAnalyzer) checkSlowIndexing(data *collector.CollectedData) *finding.Finding {
	if len(data.Tasks) == 0 {
		return nil
	}

	// Filter for successful indexing tasks with duration
	var durations []float64
	for _, task := range data.Tasks {
		if task.Status != "succeeded" {
			continue
		}
		if task.Type != "documentAdditionOrUpdate" && task.Type != "documentDeletion" {
			continue
		}
		if task.Duration == "" {
			continue
		}

		// Parse ISO 8601 duration (e.g., "PT1.234S" or "PT1M30.5S")
		duration := parseDuration(task.Duration)
		if duration > 0 {
			durations = append(durations, duration)
		}
	}

	if len(durations) == 0 {
		return nil
	}

	// Calculate average duration
	var totalDuration float64
	for _, d := range durations {
		totalDuration += d
	}
	avgDuration := totalDuration / float64(len(durations))

	// P002: Average duration > 5 minutes (300 seconds)
	if avgDuration > 300 {
		return finding.New(
			"MEILI-P002",
			"Slow indexing operations",
			fmt.Sprintf("Average indexing task duration is %.1f minutes. Consider optimizing document size or batch sizes.", avgDuration/60),
			finding.SeverityWarning,
			finding.CategoryPerformance,
		).WithRecommendation("Consider reducing document size, batching fewer documents per request, or checking for resource constraints.").
			WithDetails(map[string]interface{}{
				"avg_duration_seconds": avgDuration,
				"avg_duration_minutes": avgDuration / 60,
				"tasks_analyzed":       len(durations),
			})
	}

	return nil
}

// P007: Task queue backlog
func (a *PerformanceAnalyzer) checkTaskBacklog(data *collector.CollectedData) *finding.Finding {
	if len(data.Tasks) < 10 {
		return nil
	}

	// Calculate queue times for tasks with both enqueued and started timestamps
	var queueTimes []float64
	for _, task := range data.Tasks {
		if task.EnqueuedAt == nil || task.StartedAt == nil {
			continue
		}
		queueTime := task.StartedAt.Sub(*task.EnqueuedAt).Seconds()
		if queueTime >= 0 {
			queueTimes = append(queueTimes, queueTime)
		}
	}

	if len(queueTimes) < 5 {
		return nil
	}

	// Calculate average and max queue time
	var totalQueueTime float64
	var maxQueueTime float64
	for _, qt := range queueTimes {
		totalQueueTime += qt
		if qt > maxQueueTime {
			maxQueueTime = qt
		}
	}
	avgQueueTime := totalQueueTime / float64(len(queueTimes))

	// Count tasks with significant delay (>30s)
	var delayedCount int
	for _, qt := range queueTimes {
		if qt > 30 {
			delayedCount++
		}
	}

	// P007: Average queue time > 60 seconds
	if avgQueueTime > 60 {
		return finding.New(
			"MEILI-P007",
			"Sustained task queue backlog detected",
			fmt.Sprintf("Tasks are waiting an average of %.0f seconds in the queue before processing starts (max: %.0fs). %d of %d analyzed tasks had delays > 30s. This suggests the instance may be overloaded.", avgQueueTime, maxQueueTime, delayedCount, len(queueTimes)),
			finding.SeverityWarning,
			finding.CategoryPerformance,
		).WithRecommendation("Consider scaling up the instance, reducing indexing frequency, or batching operations more efficiently.").
			WithDetails(map[string]interface{}{
				"avg_queue_time_seconds": avgQueueTime,
				"max_queue_time_seconds": maxQueueTime,
				"tasks_analyzed":         len(queueTimes),
				"tasks_delayed":          delayedCount,
			})
	}

	return nil
}

// parseDuration parses an ISO 8601 duration string and returns seconds
func parseDuration(s string) float64 {
	matches := durationRegex.FindStringSubmatch(s)
	if matches == nil {
		return 0
	}

	var seconds float64
	// Minutes (optional)
	if matches[1] != "" {
		var minutes float64
		fmt.Sscanf(matches[1], "%f", &minutes)
		seconds += minutes * 60
	}
	// Seconds
	if matches[2] != "" {
		var secs float64
		fmt.Sscanf(matches[2], "%f", &secs)
		seconds += secs
	}
	return seconds
}
