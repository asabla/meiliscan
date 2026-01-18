package cli

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/asabla/meiliscan/internal/analyzer"
	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/exporter"
	"github.com/asabla/meiliscan/internal/report"
	"github.com/spf13/cobra"
)

var (
	analyzeURL    string
	analyzeAPIKey string
	analyzeOutput string
	analyzeFormat string
	analyzeCI     bool
)

var analyzeCmd = &cobra.Command{
	Use:   "analyze",
	Short: "Analyze a Meilisearch instance or dump file",
	Long: `Analyze a Meilisearch instance or dump file to identify potential issues,
optimization opportunities, and provide actionable recommendations.

Examples:
  # Analyze a live instance
  meiliscan analyze --url http://localhost:7700

  # With API key
  meiliscan analyze --url http://localhost:7700 --api-key your-master-key

  # Save results to file
  meiliscan analyze --url http://localhost:7700 --output analysis.json`,
	RunE: runAnalyze,
}

func init() {
	rootCmd.AddCommand(analyzeCmd)

	analyzeCmd.Flags().StringVarP(&analyzeURL, "url", "u", "", "Meilisearch instance URL")
	analyzeCmd.Flags().StringVarP(&analyzeAPIKey, "api-key", "k", "", "Meilisearch API key (or set MEILI_MASTER_KEY env var)")
	analyzeCmd.Flags().StringVarP(&analyzeOutput, "output", "o", "", "Output file path")
	analyzeCmd.Flags().StringVarP(&analyzeFormat, "format", "f", "json", "Output format: json, markdown")
	analyzeCmd.Flags().BoolVar(&analyzeCI, "ci", false, "CI mode - exit with non-zero code on findings")
}

func runAnalyze(cmd *cobra.Command, args []string) error {
	// Validate inputs
	if analyzeURL == "" {
		return fmt.Errorf("--url is required for live instance analysis")
	}

	// Check for API key in environment if not provided
	apiKey := analyzeAPIKey
	if apiKey == "" {
		apiKey = os.Getenv("MEILI_MASTER_KEY")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	// Create collector
	coll := collector.NewLiveCollector(analyzeURL, apiKey)

	// Collect data
	fmt.Fprintf(os.Stderr, "Connecting to %s...\n", analyzeURL)
	data, err := coll.Collect(ctx)
	if err != nil {
		return fmt.Errorf("failed to collect data: %w", err)
	}

	fmt.Fprintf(os.Stderr, "Found %d indexes, analyzing...\n", len(data.Indexes))

	// Run analyzers
	registry := analyzer.NewRegistry()
	findings := registry.Analyze(data)

	// Build report
	rpt := report.New(data, findings)

	// Export
	var exp exporter.Exporter
	switch analyzeFormat {
	case "json":
		exp = exporter.NewJSON()
	case "markdown":
		exp = exporter.NewMarkdown()
	default:
		return fmt.Errorf("unknown format: %s", analyzeFormat)
	}

	output, err := exp.Export(rpt)
	if err != nil {
		return fmt.Errorf("failed to export report: %w", err)
	}

	// Write output
	if analyzeOutput != "" {
		if err := os.WriteFile(analyzeOutput, output, 0644); err != nil {
			return fmt.Errorf("failed to write output: %w", err)
		}
		fmt.Fprintf(os.Stderr, "Report saved to %s\n", analyzeOutput)
	} else {
		fmt.Println(string(output))
	}

	// Print summary to stderr
	printSummary(rpt)

	// CI mode exit codes
	if analyzeCI {
		if rpt.Summary.CriticalCount > 0 {
			return fmt.Errorf("found %d critical issues", rpt.Summary.CriticalCount)
		}
	}

	return nil
}

func printSummary(rpt *report.Report) {
	summary := map[string]interface{}{
		"health_score": rpt.Summary.HealthScore,
		"findings": map[string]int{
			"critical":   rpt.Summary.CriticalCount,
			"warning":    rpt.Summary.WarningCount,
			"suggestion": rpt.Summary.SuggestionCount,
			"info":       rpt.Summary.InfoCount,
		},
	}

	summaryJSON, _ := json.MarshalIndent(summary, "", "  ")
	fmt.Fprintf(os.Stderr, "\nSummary:\n%s\n", string(summaryJSON))
}
