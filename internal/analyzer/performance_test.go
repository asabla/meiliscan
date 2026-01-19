package analyzer

import (
	"testing"

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
