package cli

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/asabla/meiliscan/internal/analyzer"
	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/report"
	"github.com/spf13/cobra"
)

var (
	summaryURL    string
	summaryAPIKey string
	summaryDump   string
)

var summaryCmd = &cobra.Command{
	Use:   "summary",
	Short: "Quick health check summary",
	Long: `Get a quick overview of your Meilisearch instance or dump file health.

This command provides a condensed view showing:
- Health score
- Instance statistics  
- Finding counts by severity

Examples:
  # Check a live instance
  meiliscan summary --url http://localhost:7700

  # Check a dump file
  meiliscan summary --dump ./path/to/dump.dump`,
	RunE: runSummary,
}

func init() {
	rootCmd.AddCommand(summaryCmd)

	summaryCmd.Flags().StringVarP(&summaryURL, "url", "u", "", "Meilisearch instance URL")
	summaryCmd.Flags().StringVarP(&summaryAPIKey, "api-key", "k", "", "Meilisearch API key")
	summaryCmd.Flags().StringVarP(&summaryDump, "dump", "d", "", "Path to a Meilisearch dump file")
}

func runSummary(cmd *cobra.Command, args []string) error {
	// Validate inputs
	if summaryURL == "" && summaryDump == "" {
		return fmt.Errorf("either --url or --dump is required")
	}
	if summaryURL != "" && summaryDump != "" {
		return fmt.Errorf("cannot specify both --url and --dump")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	var coll collector.Collector

	if summaryDump != "" {
		if _, err := os.Stat(summaryDump); os.IsNotExist(err) {
			return fmt.Errorf("dump file not found: %s", summaryDump)
		}
		coll = collector.NewDumpCollector(summaryDump, 50) // Smaller sample for quick summary
	} else {
		apiKey := summaryAPIKey
		if apiKey == "" {
			apiKey = os.Getenv("MEILI_MASTER_KEY")
		}
		coll = collector.NewLiveCollector(summaryURL, apiKey)
	}

	// Collect data
	data, err := coll.Collect(ctx)
	if err != nil {
		return fmt.Errorf("failed to collect data: %w", err)
	}

	// Run analyzers
	registry := analyzer.NewRegistry()
	findings := registry.Analyze(data)

	// Build report
	rpt := report.New(data, findings)

	// Render summary only
	renderer := NewRenderer()
	fmt.Println(renderer.RenderSummary(rpt))

	return nil
}
