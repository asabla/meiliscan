package exporter

import (
	"bytes"
	"fmt"
	"strings"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

// MarkdownExporter exports reports as Markdown.
type MarkdownExporter struct{}

// NewMarkdown creates a new MarkdownExporter.
func NewMarkdown() *MarkdownExporter {
	return &MarkdownExporter{}
}

// Export converts the report to Markdown.
func (e *MarkdownExporter) Export(r *report.Report) ([]byte, error) {
	var buf bytes.Buffer

	// Header
	buf.WriteString("# Meiliscan Analysis Report\n\n")

	// Instance info
	buf.WriteString("## Instance Information\n\n")
	buf.WriteString(fmt.Sprintf("- **Version**: %s\n", r.Instance.Version))
	buf.WriteString(fmt.Sprintf("- **Indexes**: %d\n", r.Instance.IndexCount))
	buf.WriteString(fmt.Sprintf("- **Total Documents**: %d\n", r.Instance.TotalDocuments))
	buf.WriteString(fmt.Sprintf("- **Database Size**: %s\n", formatBytes(r.Instance.DatabaseSize)))
	buf.WriteString("\n")

	// Summary
	buf.WriteString("## Summary\n\n")
	buf.WriteString(fmt.Sprintf("**Health Score**: %d/100 (%s)\n\n", r.Summary.HealthScore, r.Summary.HealthStatus))
	buf.WriteString("| Severity | Count |\n")
	buf.WriteString("|----------|-------|\n")
	buf.WriteString(fmt.Sprintf("| Critical | %d |\n", r.Summary.CriticalCount))
	buf.WriteString(fmt.Sprintf("| Warning | %d |\n", r.Summary.WarningCount))
	buf.WriteString(fmt.Sprintf("| Suggestion | %d |\n", r.Summary.SuggestionCount))
	buf.WriteString(fmt.Sprintf("| Info | %d |\n", r.Summary.InfoCount))
	buf.WriteString("\n")

	// Findings
	if len(r.Findings) > 0 {
		buf.WriteString("## Findings\n\n")

		for _, f := range r.Findings {
			icon := severityIcon(f.Severity)
			buf.WriteString(fmt.Sprintf("### %s %s: %s\n\n", icon, f.ID, f.Title))

			if f.IndexUID != "" {
				buf.WriteString(fmt.Sprintf("**Index**: `%s`\n\n", f.IndexUID))
			}

			buf.WriteString(f.Description + "\n\n")

			if f.Recommendation != "" {
				buf.WriteString(fmt.Sprintf("**Recommendation**: %s\n\n", f.Recommendation))
			}

			if f.FixCommand != "" {
				buf.WriteString("**Fix Command**:\n```bash\n" + f.FixCommand + "\n```\n\n")
			}

			buf.WriteString("---\n\n")
		}
	} else {
		buf.WriteString("## Findings\n\nNo issues found! Your Meilisearch instance looks healthy.\n\n")
	}

	// Footer
	buf.WriteString(fmt.Sprintf("\n---\n*Generated at %s by Meiliscan*\n", r.GeneratedAt.Format("2006-01-02 15:04:05 MST")))

	return buf.Bytes(), nil
}

func severityIcon(s finding.Severity) string {
	switch s {
	case finding.SeverityCritical:
		return "[CRITICAL]"
	case finding.SeverityWarning:
		return "[WARNING]"
	case finding.SeveritySuggestion:
		return "[SUGGESTION]"
	case finding.SeverityInfo:
		return "[INFO]"
	default:
		return ""
	}
}

func formatBytes(b int64) string {
	const unit = 1024
	if b < unit {
		return fmt.Sprintf("%d B", b)
	}
	div, exp := int64(unit), 0
	for n := b / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(b)/float64(div), "KMGTPE"[exp])
}

// Escape markdown special characters in text
func escapeMarkdown(s string) string {
	replacer := strings.NewReplacer(
		"*", "\\*",
		"_", "\\_",
		"`", "\\`",
		"#", "\\#",
	)
	return replacer.Replace(s)
}
