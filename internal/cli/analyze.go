package cli

import (
	"context"
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
	analyzeURL        string
	analyzeAPIKey     string
	analyzeDump       string
	analyzeOutput     string
	analyzeFormat     string
	analyzeCI         bool
	analyzeSampleDocs int
	analyzePretty     bool
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

  # Analyze a dump file
  meiliscan analyze --dump ./path/to/dump.dump

  # Save results to file
  meiliscan analyze --url http://localhost:7700 --output analysis.json

  # Export as Markdown
  meiliscan analyze --dump ./dump.dump --format markdown --output report.md`,
	RunE: runAnalyze,
}

func init() {
	rootCmd.AddCommand(analyzeCmd)

	analyzeCmd.Flags().StringVarP(&analyzeURL, "url", "u", "", "Meilisearch instance URL")
	analyzeCmd.Flags().StringVarP(&analyzeAPIKey, "api-key", "k", "", "Meilisearch API key (or set MEILI_MASTER_KEY env var)")
	analyzeCmd.Flags().StringVarP(&analyzeDump, "dump", "d", "", "Path to a Meilisearch dump file")
	analyzeCmd.Flags().StringVarP(&analyzeOutput, "output", "o", "", "Output file path")
	analyzeCmd.Flags().StringVarP(&analyzeFormat, "format", "f", "pretty", "Output format: pretty, json, markdown")
	analyzeCmd.Flags().BoolVar(&analyzeCI, "ci", false, "CI mode - exit with non-zero code on critical findings")
	analyzeCmd.Flags().IntVar(&analyzeSampleDocs, "sample-documents", 100, "Number of sample documents to load per index (dump mode)")
}

func runAnalyze(cmd *cobra.Command, args []string) error {
	// Validate inputs - need either URL or dump
	if analyzeURL == "" && analyzeDump == "" {
		return fmt.Errorf("either --url or --dump is required")
	}
	if analyzeURL != "" && analyzeDump != "" {
		return fmt.Errorf("cannot specify both --url and --dump")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	var coll collector.Collector
	var sourceDesc string

	if analyzeDump != "" {
		// Dump file analysis
		if _, err := os.Stat(analyzeDump); os.IsNotExist(err) {
			return fmt.Errorf("dump file not found: %s", analyzeDump)
		}
		coll = collector.NewDumpCollector(analyzeDump, analyzeSampleDocs)
		sourceDesc = analyzeDump
		fmt.Fprintf(os.Stderr, "Parsing dump file: %s...\n", analyzeDump)
	} else {
		// Live instance analysis
		apiKey := analyzeAPIKey
		if apiKey == "" {
			apiKey = os.Getenv("MEILI_MASTER_KEY")
		}
		coll = collector.NewLiveCollector(analyzeURL, apiKey)
		sourceDesc = analyzeURL
		fmt.Fprintf(os.Stderr, "Connecting to %s...\n", analyzeURL)
	}

	// Collect data
	data, err := coll.Collect(ctx)
	if err != nil {
		return fmt.Errorf("failed to collect data from %s: %w", sourceDesc, err)
	}

	fmt.Fprintf(os.Stderr, "Found %d indexes, analyzing...\n", len(data.Indexes))

	// Run analyzers
	registry := analyzer.NewRegistry()
	findings := registry.Analyze(data)

	// Build report
	rpt := report.New(data, findings)

	// Handle output format
	switch analyzeFormat {
	case "pretty":
		// Styled terminal output
		renderer := NewRenderer()
		output := renderer.RenderReport(rpt)

		if analyzeOutput != "" {
			// Strip ANSI codes for file output
			if err := os.WriteFile(analyzeOutput, []byte(output), 0644); err != nil {
				return fmt.Errorf("failed to write output: %w", err)
			}
			fmt.Fprintf(os.Stderr, "Report saved to %s\n", analyzeOutput)
		} else {
			fmt.Println(output)
		}

	case "json", "markdown":
		var exp exporter.Exporter
		if analyzeFormat == "json" {
			exp = exporter.NewJSON()
		} else {
			exp = exporter.NewMarkdown()
		}

		output, err := exp.Export(rpt)
		if err != nil {
			return fmt.Errorf("failed to export report: %w", err)
		}

		if analyzeOutput != "" {
			if err := os.WriteFile(analyzeOutput, output, 0644); err != nil {
				return fmt.Errorf("failed to write output: %w", err)
			}
			fmt.Fprintf(os.Stderr, "Report saved to %s\n", analyzeOutput)
		} else {
			fmt.Println(string(output))
		}

	default:
		return fmt.Errorf("unknown format: %s (valid: pretty, json, markdown)", analyzeFormat)
	}

	// CI mode exit codes
	if analyzeCI && rpt.Summary.CriticalCount > 0 {
		return fmt.Errorf("found %d critical issues", rpt.Summary.CriticalCount)
	}

	return nil
}
