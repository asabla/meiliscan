package analyzer

import (
	"fmt"
	"testing"
	"time"

	"github.com/asabla/meiliscan/internal/collector"
)

func TestPerformanceAnalyzer_TooManyIndexes(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		indexCount  int
		expectFound bool
	}{
		{
			name:        "50 indexes triggers P004",
			indexCount:  50,
			expectFound: true,
		},
		{
			name:        "100 indexes triggers P004",
			indexCount:  100,
			expectFound: true,
		},
		{
			name:        "49 indexes does not trigger P004",
			indexCount:  49,
			expectFound: false,
		},
		{
			name:        "5 indexes does not trigger P004",
			indexCount:  5,
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			indexes := make([]collector.IndexData, tt.indexCount)
			for i := 0; i < tt.indexCount; i++ {
				indexes[i] = collector.IndexData{UID: "test-index"}
			}

			data := &collector.CollectedData{
				Indexes: indexes,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P004" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P004 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P008: Many tiny indexing tasks
func TestPerformanceAnalyzer_TinyIndexingTasks(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		tasks       []collector.Task
		expectFound bool
	}{
		{
			name: "many tiny tasks triggers P008",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 25)
				for i := 0; i < 25; i++ {
					tasks[i] = collector.Task{
						UID:    int64(i),
						Type:   "documentAdditionOrUpdate",
						Status: "succeeded",
						Details: collector.TaskDetails{
							ReceivedDocuments: 5, // tiny: < 10 docs
						},
					}
				}
				return tasks
			}(),
			expectFound: true,
		},
		{
			name: "mixed task sizes does not trigger P008",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 20)
				for i := 0; i < 10; i++ {
					tasks[i] = collector.Task{
						UID:    int64(i),
						Type:   "documentAdditionOrUpdate",
						Status: "succeeded",
						Details: collector.TaskDetails{
							ReceivedDocuments: 5, // tiny
						},
					}
				}
				for i := 10; i < 20; i++ {
					tasks[i] = collector.Task{
						UID:    int64(i),
						Type:   "documentAdditionOrUpdate",
						Status: "succeeded",
						Details: collector.TaskDetails{
							ReceivedDocuments: 100, // normal
						},
					}
				}
				return tasks
			}(),
			expectFound: false, // 50% tiny but only 10 tiny tasks
		},
		{
			name: "not enough tasks does not trigger P008",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 10)
				for i := 0; i < 10; i++ {
					tasks[i] = collector.Task{
						UID:    int64(i),
						Type:   "documentAdditionOrUpdate",
						Status: "succeeded",
						Details: collector.TaskDetails{
							ReceivedDocuments: 5,
						},
					}
				}
				return tasks
			}(),
			expectFound: false, // less than 20 tasks
		},
		{
			name: "large batches do not trigger P008",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 25)
				for i := 0; i < 25; i++ {
					tasks[i] = collector.Task{
						UID:    int64(i),
						Type:   "documentAdditionOrUpdate",
						Status: "succeeded",
						Details: collector.TaskDetails{
							ReceivedDocuments: 1000,
						},
					}
				}
				return tasks
			}(),
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Tasks: tt.tasks,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P008" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P008 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P009: Oversized indexing tasks
func TestPerformanceAnalyzer_OversizedIndexingTasks(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		tasks       []collector.Task
		expectFound bool
	}{
		{
			name: "slow task triggers P009",
			tasks: []collector.Task{
				{
					UID:      1,
					Type:     "documentAdditionOrUpdate",
					Status:   "succeeded",
					Duration: "PT15M30S", // 15 minutes 30 seconds > 10 minutes
					Details: collector.TaskDetails{
						ReceivedDocuments: 100000,
					},
				},
			},
			expectFound: true,
		},
		{
			name: "very slow task triggers P009",
			tasks: []collector.Task{
				{
					UID:      1,
					Type:     "documentAdditionOrUpdate",
					Status:   "succeeded",
					Duration: "PT1800S", // 30 minutes
					Details: collector.TaskDetails{
						ReceivedDocuments: 500000,
					},
				},
			},
			expectFound: true,
		},
		{
			name: "fast tasks do not trigger P009",
			tasks: []collector.Task{
				{
					UID:      1,
					Type:     "documentAdditionOrUpdate",
					Status:   "succeeded",
					Duration: "PT30S", // 30 seconds
					Details: collector.TaskDetails{
						ReceivedDocuments: 1000,
					},
				},
				{
					UID:      2,
					Type:     "documentAdditionOrUpdate",
					Status:   "succeeded",
					Duration: "PT5M0S", // 5 minutes
					Details: collector.TaskDetails{
						ReceivedDocuments: 10000,
					},
				},
			},
			expectFound: false,
		},
		{
			name:        "no tasks does not trigger P009",
			tasks:       []collector.Task{},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Tasks: tt.tasks,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P009" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P009 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P010: Recurring task failures
func TestPerformanceAnalyzer_RecurringFailures(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		tasks       []collector.Task
		expectFound bool
	}{
		{
			name: "recurring failures triggers P010",
			tasks: []collector.Task{
				{
					UID:    1,
					Status: "failed",
					Error: &collector.TaskError{
						Code:    "invalid_document_id",
						Message: "Document identifier is invalid",
					},
				},
				{
					UID:    2,
					Status: "failed",
					Error: &collector.TaskError{
						Code:    "invalid_document_id",
						Message: "Document identifier is invalid",
					},
				},
				{
					UID:    3,
					Status: "failed",
					Error: &collector.TaskError{
						Code:    "invalid_document_id",
						Message: "Document identifier is invalid",
					},
				},
			},
			expectFound: true, // 3 failures with same code
		},
		{
			name: "multiple error types triggers P010",
			tasks: []collector.Task{
				{UID: 1, Status: "failed", Error: &collector.TaskError{Code: "error_a", Message: "Error A"}},
				{UID: 2, Status: "failed", Error: &collector.TaskError{Code: "error_a", Message: "Error A"}},
				{UID: 3, Status: "failed", Error: &collector.TaskError{Code: "error_a", Message: "Error A"}},
				{UID: 4, Status: "failed", Error: &collector.TaskError{Code: "error_b", Message: "Error B"}},
				{UID: 5, Status: "failed", Error: &collector.TaskError{Code: "error_b", Message: "Error B"}},
				{UID: 6, Status: "failed", Error: &collector.TaskError{Code: "error_b", Message: "Error B"}},
			},
			expectFound: true,
		},
		{
			name: "few failures does not trigger P010",
			tasks: []collector.Task{
				{
					UID:    1,
					Status: "failed",
					Error: &collector.TaskError{
						Code:    "invalid_document_id",
						Message: "Document identifier is invalid",
					},
				},
				{
					UID:    2,
					Status: "failed",
					Error: &collector.TaskError{
						Code:    "invalid_document_id",
						Message: "Document identifier is invalid",
					},
				},
			},
			expectFound: false, // only 2 failures
		},
		{
			name: "different error codes does not trigger P010",
			tasks: []collector.Task{
				{UID: 1, Status: "failed", Error: &collector.TaskError{Code: "error_a", Message: "A"}},
				{UID: 2, Status: "failed", Error: &collector.TaskError{Code: "error_b", Message: "B"}},
				{UID: 3, Status: "failed", Error: &collector.TaskError{Code: "error_c", Message: "C"}},
			},
			expectFound: false, // no recurring pattern
		},
		{
			name: "no failed tasks does not trigger P010",
			tasks: []collector.Task{
				{UID: 1, Status: "succeeded"},
				{UID: 2, Status: "succeeded"},
			},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Tasks: tt.tasks,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P010" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P010 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P003: Database fragmentation detection
func TestPerformanceAnalyzer_DatabaseFragmentation(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		stats       *collector.Stats
		expectFound bool
	}{
		{
			name: "high fragmentation triggers P003",
			stats: &collector.Stats{
				DatabaseSize:     100000000, // 100 MB total
				UsedDatabaseSize: 40000000,  // 40 MB used (40% utilization = 60% fragmentation)
			},
			expectFound: true,
		},
		{
			name: "very high fragmentation triggers P003",
			stats: &collector.Stats{
				DatabaseSize:     100000000, // 100 MB total
				UsedDatabaseSize: 30000000,  // 30 MB used (30% utilization = 70% fragmentation)
			},
			expectFound: true,
		},
		{
			name: "normal utilization does not trigger P003",
			stats: &collector.Stats{
				DatabaseSize:     100000000, // 100 MB total
				UsedDatabaseSize: 80000000,  // 80 MB used (80% utilization)
			},
			expectFound: false,
		},
		{
			name: "exactly at threshold does not trigger P003",
			stats: &collector.Stats{
				DatabaseSize:     100000000, // 100 MB total
				UsedDatabaseSize: 60000000,  // 60 MB used (60% utilization)
			},
			expectFound: false,
		},
		{
			name:        "nil stats does not trigger P003",
			stats:       nil,
			expectFound: false,
		},
		{
			name: "zero database size does not trigger P003",
			stats: &collector.Stats{
				DatabaseSize:     0,
				UsedDatabaseSize: 0,
			},
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Stats: tt.stats,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P003" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P003 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P005: Index imbalance detection
func TestPerformanceAnalyzer_IndexImbalance(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		indexes     []collector.IndexData
		expectFound bool
	}{
		{
			name: "dominant index triggers P005",
			indexes: []collector.IndexData{
				{UID: "large", NumberOfDocuments: 1000000},
				{UID: "small1", NumberOfDocuments: 50000},
				{UID: "small2", NumberOfDocuments: 50000},
			},
			expectFound: true, // large has ~91% of documents
		},
		{
			name: "exactly 80% triggers P005",
			indexes: []collector.IndexData{
				{UID: "large", NumberOfDocuments: 80000},
				{UID: "small", NumberOfDocuments: 19999}, // > 80%
			},
			expectFound: true,
		},
		{
			name: "balanced indexes do not trigger P005",
			indexes: []collector.IndexData{
				{UID: "idx1", NumberOfDocuments: 100000},
				{UID: "idx2", NumberOfDocuments: 80000},
				{UID: "idx3", NumberOfDocuments: 70000},
			},
			expectFound: false, // largest is 40%
		},
		{
			name: "single index does not trigger P005",
			indexes: []collector.IndexData{
				{UID: "only", NumberOfDocuments: 100000},
			},
			expectFound: false, // need at least 2 indexes
		},
		{
			name: "empty indexes do not trigger P005",
			indexes: []collector.IndexData{
				{UID: "empty1", NumberOfDocuments: 0},
				{UID: "empty2", NumberOfDocuments: 0},
			},
			expectFound: false, // totalDocs = 0
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: tt.indexes,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P005" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P005 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P007: Task queue backlog detection
func TestPerformanceAnalyzer_TaskBacklog(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	now := time.Now()

	tests := []struct {
		name        string
		tasks       []collector.Task
		expectFound bool
	}{
		{
			name: "high average queue time triggers P007",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 10)
				for i := 0; i < 10; i++ {
					enqueued := now.Add(-time.Duration(i)*time.Minute - 2*time.Minute)
					started := now.Add(-time.Duration(i) * time.Minute)
					tasks[i] = collector.Task{
						UID:        int64(i),
						Status:     "succeeded",
						EnqueuedAt: &enqueued,
						StartedAt:  &started,
					}
				}
				return tasks
			}(),
			expectFound: true, // avg 2 minutes queue time > 60 seconds
		},
		{
			name: "low queue time does not trigger P007",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 10)
				for i := 0; i < 10; i++ {
					enqueued := now.Add(-time.Duration(i)*time.Minute - 10*time.Second)
					started := now.Add(-time.Duration(i) * time.Minute)
					tasks[i] = collector.Task{
						UID:        int64(i),
						Status:     "succeeded",
						EnqueuedAt: &enqueued,
						StartedAt:  &started,
					}
				}
				return tasks
			}(),
			expectFound: false, // avg 10 seconds < 60 seconds
		},
		{
			name: "not enough tasks does not trigger P007",
			tasks: func() []collector.Task {
				enqueued := now.Add(-5 * time.Minute)
				started := now.Add(-3 * time.Minute)
				return []collector.Task{
					{UID: 1, Status: "succeeded", EnqueuedAt: &enqueued, StartedAt: &started},
				}
			}(),
			expectFound: false, // < 10 tasks
		},
		{
			name: "tasks without timestamps",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 10)
				for i := 0; i < 10; i++ {
					tasks[i] = collector.Task{
						UID:    int64(i),
						Status: "succeeded",
					}
				}
				return tasks
			}(),
			expectFound: false, // no timestamps to calculate queue time
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Tasks: tt.tasks,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P007" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P007 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P006: Too many fields detection
func TestPerformanceAnalyzer_FieldCount(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		fieldDist   map[string]int64
		expectFound bool
	}{
		{
			name: "too many fields triggers P006",
			fieldDist: func() map[string]int64 {
				m := make(map[string]int64)
				for i := 0; i < 150; i++ {
					m[fmt.Sprintf("field%d", i)] = 100
				}
				return m
			}(),
			expectFound: true,
		},
		{
			name: "normal field count does not trigger P006",
			fieldDist: map[string]int64{
				"id": 100, "name": 100, "title": 100, "description": 100,
			},
			expectFound: false,
		},
		{
			name: "exactly 100 fields does not trigger P006",
			fieldDist: func() map[string]int64 {
				m := make(map[string]int64)
				for i := 0; i < 100; i++ {
					m[fmt.Sprintf("field%d", i)] = 100
				}
				return m
			}(),
			expectFound: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Indexes: []collector.IndexData{
					{
						UID:               "test-index",
						FieldDistribution: tt.fieldDist,
					},
				},
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P006" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P006 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// P001: Task failure rate detection
func TestPerformanceAnalyzer_TaskFailures(t *testing.T) {
	analyzer := NewPerformanceAnalyzer()

	tests := []struct {
		name        string
		tasks       []collector.Task
		expectFound bool
	}{
		{
			name: "high failure rate triggers P001",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 20)
				for i := 0; i < 20; i++ {
					status := "succeeded"
					if i < 5 { // 25% failure rate
						status = "failed"
					}
					tasks[i] = collector.Task{
						UID:    int64(i),
						Status: status,
					}
				}
				return tasks
			}(),
			expectFound: true, // > 10% failure rate
		},
		{
			name: "low failure rate does not trigger P001",
			tasks: func() []collector.Task {
				tasks := make([]collector.Task, 100)
				for i := 0; i < 100; i++ {
					status := "succeeded"
					if i == 0 { // 1% failure rate
						status = "failed"
					}
					tasks[i] = collector.Task{
						UID:    int64(i),
						Status: status,
					}
				}
				return tasks
			}(),
			expectFound: false, // < 10% failure rate
		},
		{
			name: "not enough tasks does not trigger P001",
			tasks: []collector.Task{
				{UID: 1, Status: "failed"},
				{UID: 2, Status: "failed"},
			},
			expectFound: false, // < 10 tasks
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := &collector.CollectedData{
				Tasks: tt.tasks,
			}

			findings := analyzer.Analyze(data)

			var found bool
			for _, f := range findings {
				if f.ID == "MEILI-P001" {
					found = true
					break
				}
			}

			if found != tt.expectFound {
				t.Errorf("expected P001 found=%v, got %v", tt.expectFound, found)
			}
		})
	}
}

// Test helper: getDocumentCount
func TestHelperFunction_GetDocumentCount(t *testing.T) {
	tests := []struct {
		name     string
		task     collector.Task
		expected int64
	}{
		{
			name: "received documents",
			task: collector.Task{
				Details: collector.TaskDetails{
					ReceivedDocuments: 100,
				},
			},
			expected: 100,
		},
		{
			name: "indexed documents fallback",
			task: collector.Task{
				Details: collector.TaskDetails{
					IndexedDocuments: 50,
				},
			},
			expected: 50,
		},
		{
			name: "provided ids fallback",
			task: collector.Task{
				Details: collector.TaskDetails{
					ProvidedIds: 25,
				},
			},
			expected: 25,
		},
		{
			name: "received takes priority",
			task: collector.Task{
				Details: collector.TaskDetails{
					ReceivedDocuments: 100,
					IndexedDocuments:  90,
					ProvidedIds:       80,
				},
			},
			expected: 100,
		},
		{
			name: "no documents",
			task: collector.Task{
				Details: collector.TaskDetails{},
			},
			expected: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := getDocumentCount(tt.task)
			if result != tt.expected {
				t.Errorf("expected %d, got %d", tt.expected, result)
			}
		})
	}
}
