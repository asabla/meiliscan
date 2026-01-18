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
