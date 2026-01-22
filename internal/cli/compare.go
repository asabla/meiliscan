package cli

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/asabla/meiliscan/internal/comparison"
	"github.com/asabla/meiliscan/internal/report"
	"github.com/spf13/cobra"
)

var (
	compareOutput string
	compareFormat string
)

var compareCmd = &cobra.Command{
	Use:   "compare <old-report.json> <new-report.json>",
	Short: "Compare two analysis reports to track changes over time",
	Long: `Compare two analysis reports to identify trends, improvements,
and regressions in your Meilisearch configuration over time.

This is useful for:
- Tracking configuration health over time
- Identifying new or resolved issues after making changes
- Understanding the impact of optimizations

Examples:
  # Compare two reports (outputs to stdout)
  meiliscan compare baseline.json current.json

  # Save comparison as JSON
  meiliscan compare baseline.json current.json --output diff.json

  # Export as Markdown
  meiliscan compare baseline.json current.json --format markdown --output diff.md`,
	Args: cobra.ExactArgs(2),
	RunE: runCompare,
}

func init() {
	compareCmd.Flags().StringVarP(&compareOutput, "output", "o", "", "Output file path (default: stdout)")
	compareCmd.Flags().StringVarP(&compareFormat, "format", "f", "markdown", "Output format: json, markdown")

	rootCmd.AddCommand(compareCmd)
}

func runCompare(cmd *cobra.Command, args []string) error {
	oldPath := args[0]
	newPath := args[1]

	// Load old report
	oldReport, err := loadReport(oldPath)
	if err != nil {
		return fmt.Errorf("failed to load old report %s: %w", oldPath, err)
	}

	// Load new report
	newReport, err := loadReport(newPath)
	if err != nil {
		return fmt.Errorf("failed to load new report %s: %w", newPath, err)
	}

	// Compare reports
	compReport := comparison.Compare(oldReport, newReport)

	// Format output
	var output string
	switch strings.ToLower(compareFormat) {
	case "json":
		data, err := json.MarshalIndent(compReport, "", "  ")
		if err != nil {
			return fmt.Errorf("failed to marshal comparison: %w", err)
		}
		output = string(data)
	case "markdown", "md":
		output = formatComparisonMarkdown(compReport)
	default:
		return fmt.Errorf("unsupported format: %s (use json or markdown)", compareFormat)
	}

	// Write output
	if compareOutput != "" {
		if err := os.WriteFile(compareOutput, []byte(output), 0644); err != nil {
			return fmt.Errorf("failed to write output: %w", err)
		}
		fmt.Printf("Comparison saved to %s\n", compareOutput)
	} else {
		fmt.Print(output)
	}

	return nil
}

func loadReport(path string) (*report.Report, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var rpt report.Report
	if err := json.Unmarshal(data, &rpt); err != nil {
		return nil, fmt.Errorf("invalid JSON: %w", err)
	}

	return &rpt, nil
}

func formatComparisonMarkdown(r *comparison.Report) string {
	var sb strings.Builder

	// Header
	sb.WriteString("# Meiliscan Comparison Report\n\n")
	sb.WriteString(fmt.Sprintf("**Generated:** %s\n\n", r.GeneratedAt.Format("2006-01-02 15:04:05")))

	// Summary box
	sb.WriteString("## Summary\n\n")
	sb.WriteString(fmt.Sprintf("| Metric | Old | New | Change |\n"))
	sb.WriteString("|--------|-----|-----|--------|\n")

	// Health Score
	healthChange := formatChange(r.Summary.HealthScore)
	sb.WriteString(fmt.Sprintf("| Health Score | %d | %d | %s |\n",
		int(*r.Summary.HealthScore.OldValue),
		int(*r.Summary.HealthScore.NewValue),
		healthChange))

	// Total Documents
	docsChange := formatChange(r.Summary.TotalDocuments)
	sb.WriteString(fmt.Sprintf("| Total Documents | %d | %d | %s |\n",
		int(*r.Summary.TotalDocuments.OldValue),
		int(*r.Summary.TotalDocuments.NewValue),
		docsChange))

	// Total Indexes
	idxChange := formatChange(r.Summary.TotalIndexes)
	sb.WriteString(fmt.Sprintf("| Total Indexes | %d | %d | %s |\n",
		int(*r.Summary.TotalIndexes.OldValue),
		int(*r.Summary.TotalIndexes.NewValue),
		idxChange))

	// Critical Issues
	critChange := formatChange(r.Summary.CriticalIssues)
	sb.WriteString(fmt.Sprintf("| Critical Issues | %d | %d | %s |\n",
		int(*r.Summary.CriticalIssues.OldValue),
		int(*r.Summary.CriticalIssues.NewValue),
		critChange))

	// Warnings
	warnChange := formatChange(r.Summary.Warnings)
	sb.WriteString(fmt.Sprintf("| Warnings | %d | %d | %s |\n",
		int(*r.Summary.Warnings.OldValue),
		int(*r.Summary.Warnings.NewValue),
		warnChange))

	sb.WriteString("\n")

	// Overall Trend
	trendEmoji := trendToEmoji(r.Summary.OverallTrend)
	sb.WriteString(fmt.Sprintf("**Overall Trend:** %s %s\n", trendEmoji, string(r.Summary.OverallTrend)))
	sb.WriteString(fmt.Sprintf("**Time Between Reports:** %s\n\n", r.Summary.TimeBetween))

	// Improvements
	if len(r.Summary.ImprovementAreas) > 0 {
		sb.WriteString("### Improvements\n\n")
		for _, area := range r.Summary.ImprovementAreas {
			sb.WriteString(fmt.Sprintf("- %s\n", area))
		}
		sb.WriteString("\n")
	}

	// Degradations
	if len(r.Summary.DegradationAreas) > 0 {
		sb.WriteString("### Degradations\n\n")
		for _, area := range r.Summary.DegradationAreas {
			sb.WriteString(fmt.Sprintf("- %s\n", area))
		}
		sb.WriteString("\n")
	}

	// Finding Changes
	if len(r.FindingChanges) > 0 {
		sb.WriteString("## Finding Changes\n\n")

		// New findings
		newFindings := filterFindingChanges(r.FindingChanges, comparison.ChangeAdded)
		if len(newFindings) > 0 {
			sb.WriteString("### New Findings\n\n")
			for _, fc := range newFindings {
				sb.WriteString(fmt.Sprintf("- **[%s]** %s (%s)\n",
					fc.Finding.ID,
					fc.Finding.Title,
					fc.Finding.Severity))
			}
			sb.WriteString("\n")
		}

		// Resolved findings
		resolvedFindings := filterFindingChanges(r.FindingChanges, comparison.ChangeRemoved)
		if len(resolvedFindings) > 0 {
			sb.WriteString("### Resolved Findings\n\n")
			for _, fc := range resolvedFindings {
				sb.WriteString(fmt.Sprintf("- **[%s]** %s (%s)\n",
					fc.Finding.ID,
					fc.Finding.Title,
					fc.Finding.Severity))
			}
			sb.WriteString("\n")
		}
	}

	// Recommendations
	if len(r.Recommendations) > 0 {
		sb.WriteString("## Recommendations\n\n")
		for i, rec := range r.Recommendations {
			sb.WriteString(fmt.Sprintf("%d. %s\n", i+1, rec))
		}
		sb.WriteString("\n")
	}

	return sb.String()
}

func formatChange(m comparison.MetricChange) string {
	if m.Change == 0 {
		return "—"
	}

	sign := "+"
	if m.Change < 0 {
		sign = ""
	}

	if m.ChangePercent != nil {
		return fmt.Sprintf("%s%.0f (%.1f%%)", sign, m.Change, *m.ChangePercent)
	}
	return fmt.Sprintf("%s%.0f", sign, m.Change)
}

func trendToEmoji(trend comparison.TrendDirection) string {
	switch trend {
	case comparison.TrendUp:
		return "📈"
	case comparison.TrendDown:
		return "📉"
	default:
		return "➡️"
	}
}

func filterFindingChanges(changes []comparison.FindingChange, changeType comparison.ChangeType) []comparison.FindingChange {
	var filtered []comparison.FindingChange
	for _, c := range changes {
		if c.ChangeType == changeType {
			filtered = append(filtered, c)
		}
	}
	return filtered
}
