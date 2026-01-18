package cli

import (
	"fmt"
	"strings"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
	"github.com/charmbracelet/lipgloss"
)

// Color palette
var (
	colorCritical   = lipgloss.Color("#FF5555")
	colorWarning    = lipgloss.Color("#FFAA00")
	colorSuggestion = lipgloss.Color("#5555FF")
	colorInfo       = lipgloss.Color("#888888")
	colorSuccess    = lipgloss.Color("#55FF55")
	colorMuted      = lipgloss.Color("#666666")
	colorAccent     = lipgloss.Color("#00AAFF")
)

// Styles
var (
	titleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(colorAccent).
			MarginBottom(1)

	healthScoreStyle = lipgloss.NewStyle().
				Bold(true).
				Padding(0, 2)

	findingHeaderStyle = lipgloss.NewStyle().
				Bold(true)

	findingIDStyle = lipgloss.NewStyle().
			Foreground(colorMuted)

	indexStyle = lipgloss.NewStyle().
			Foreground(colorAccent)

	recommendationStyle = lipgloss.NewStyle().
				Foreground(colorMuted).
				Italic(true).
				PaddingLeft(2)

	dividerStyle = lipgloss.NewStyle().
			Foreground(colorMuted)

	summaryBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(colorMuted).
			Padding(1, 2).
			MarginTop(1)

	instanceInfoStyle = lipgloss.NewStyle().
				Foreground(colorMuted)
)

// Renderer renders reports with styled output
type Renderer struct {
	width int
}

// NewRenderer creates a new styled renderer
func NewRenderer() *Renderer {
	return &Renderer{
		width: 80, // Default width
	}
}

// RenderReport renders a full report to styled output
func (r *Renderer) RenderReport(rpt *report.Report) string {
	var sb strings.Builder

	// Header
	sb.WriteString(r.renderHeader(rpt))
	sb.WriteString("\n")

	// Summary box
	sb.WriteString(r.renderSummaryBox(rpt))
	sb.WriteString("\n\n")

	// Findings by severity
	if len(rpt.Findings) > 0 {
		sb.WriteString(r.renderFindings(rpt))
	} else {
		sb.WriteString(lipgloss.NewStyle().
			Foreground(colorSuccess).
			Bold(true).
			Render("No issues found! Your Meilisearch configuration looks good."))
		sb.WriteString("\n")
	}

	return sb.String()
}

// RenderSummary renders just the summary section
func (r *Renderer) RenderSummary(rpt *report.Report) string {
	return r.renderSummaryBox(rpt)
}

func (r *Renderer) renderHeader(rpt *report.Report) string {
	title := titleStyle.Render("Meiliscan Analysis Report")

	var instanceInfo string
	if rpt.Source.Type == "live" {
		instanceInfo = fmt.Sprintf("Instance: %s | Version: %s", rpt.Source.URL, rpt.Instance.Version)
	} else {
		instanceInfo = fmt.Sprintf("Dump file: %s | Version: %s", rpt.Source.URL, rpt.Instance.Version)
	}

	return title + "\n" + instanceInfoStyle.Render(instanceInfo)
}

func (r *Renderer) renderSummaryBox(rpt *report.Report) string {
	// Health score with color based on value
	scoreColor := colorCritical
	switch {
	case rpt.Summary.HealthScore >= 80:
		scoreColor = colorSuccess
	case rpt.Summary.HealthScore >= 60:
		scoreColor = colorWarning
	case rpt.Summary.HealthScore >= 40:
		scoreColor = colorWarning
	}

	healthScore := lipgloss.NewStyle().
		Bold(true).
		Foreground(scoreColor).
		Render(fmt.Sprintf("%d", rpt.Summary.HealthScore))

	healthLabel := lipgloss.NewStyle().
		Foreground(scoreColor).
		Render(fmt.Sprintf("(%s)", rpt.Summary.HealthStatus))

	// Stats
	statsLine := fmt.Sprintf(
		"Indexes: %d | Documents: %s | Database: %s",
		rpt.Instance.IndexCount,
		formatNumber(rpt.Instance.TotalDocuments),
		formatBytes(rpt.Instance.DatabaseSize),
	)

	// Findings counts with colors
	criticalStr := severityCount(rpt.Summary.CriticalCount, "critical", colorCritical)
	warningStr := severityCount(rpt.Summary.WarningCount, "warning", colorWarning)
	suggestionStr := severityCount(rpt.Summary.SuggestionCount, "suggestion", colorSuggestion)
	infoStr := severityCount(rpt.Summary.InfoCount, "info", colorInfo)

	findingsLine := fmt.Sprintf("%s  %s  %s  %s",
		criticalStr, warningStr, suggestionStr, infoStr)

	content := fmt.Sprintf(
		"Health Score: %s %s\n\n%s\n\n%s",
		healthScore,
		healthLabel,
		instanceInfoStyle.Render(statsLine),
		findingsLine,
	)

	return summaryBoxStyle.Render(content)
}

func (r *Renderer) renderFindings(rpt *report.Report) string {
	var sb strings.Builder

	// Group findings by severity
	groups := map[finding.Severity][]*finding.Finding{
		finding.SeverityCritical:   {},
		finding.SeverityWarning:    {},
		finding.SeveritySuggestion: {},
		finding.SeverityInfo:       {},
	}

	for _, f := range rpt.Findings {
		groups[f.Severity] = append(groups[f.Severity], f)
	}

	// Render each group
	severityOrder := []finding.Severity{
		finding.SeverityCritical,
		finding.SeverityWarning,
		finding.SeveritySuggestion,
		finding.SeverityInfo,
	}

	for _, sev := range severityOrder {
		findings := groups[sev]
		if len(findings) == 0 {
			continue
		}

		// Section header
		sb.WriteString(r.renderSeverityHeader(sev, len(findings)))
		sb.WriteString("\n\n")

		// Findings
		for i, f := range findings {
			sb.WriteString(r.renderFinding(f))
			if i < len(findings)-1 {
				sb.WriteString("\n")
			}
		}
		sb.WriteString("\n")
	}

	return sb.String()
}

func (r *Renderer) renderSeverityHeader(sev finding.Severity, count int) string {
	color := severityColor(sev)
	icon := severityIcon(sev)

	style := lipgloss.NewStyle().
		Bold(true).
		Foreground(color)

	return style.Render(fmt.Sprintf("%s %s (%d)", icon, strings.ToUpper(string(sev)), count))
}

func (r *Renderer) renderFinding(f *finding.Finding) string {
	var sb strings.Builder

	color := severityColor(f.Severity)

	// Finding header: [ID] Title
	idPart := findingIDStyle.Render(fmt.Sprintf("[%s]", f.ID))
	titlePart := findingHeaderStyle.Foreground(color).Render(f.Title)

	sb.WriteString(fmt.Sprintf("%s %s", idPart, titlePart))

	// Index if present
	if f.IndexUID != "" {
		sb.WriteString(" ")
		sb.WriteString(indexStyle.Render(fmt.Sprintf("@ %s", f.IndexUID)))
	}
	sb.WriteString("\n")

	// Description
	sb.WriteString(lipgloss.NewStyle().PaddingLeft(2).Render(f.Description))
	sb.WriteString("\n")

	// Recommendation
	if f.Recommendation != "" {
		sb.WriteString(recommendationStyle.Render("-> " + f.Recommendation))
		sb.WriteString("\n")
	}

	return sb.String()
}

// Helper functions

func severityColor(sev finding.Severity) lipgloss.Color {
	switch sev {
	case finding.SeverityCritical:
		return colorCritical
	case finding.SeverityWarning:
		return colorWarning
	case finding.SeveritySuggestion:
		return colorSuggestion
	default:
		return colorInfo
	}
}

func severityIcon(sev finding.Severity) string {
	switch sev {
	case finding.SeverityCritical:
		return "X"
	case finding.SeverityWarning:
		return "!"
	case finding.SeveritySuggestion:
		return "*"
	default:
		return "i"
	}
}

func severityCount(count int, label string, color lipgloss.Color) string {
	if count == 0 {
		return lipgloss.NewStyle().Foreground(colorMuted).Render(fmt.Sprintf("%d %s", count, label))
	}
	return lipgloss.NewStyle().Foreground(color).Render(fmt.Sprintf("%d %s", count, label))
}

func formatNumber(n int64) string {
	if n >= 1_000_000 {
		return fmt.Sprintf("%.1fM", float64(n)/1_000_000)
	}
	if n >= 1_000 {
		return fmt.Sprintf("%.1fK", float64(n)/1_000)
	}
	return fmt.Sprintf("%d", n)
}

func formatBytes(b int64) string {
	if b == 0 {
		return "N/A"
	}
	if b >= 1<<30 {
		return fmt.Sprintf("%.1f GB", float64(b)/(1<<30))
	}
	if b >= 1<<20 {
		return fmt.Sprintf("%.1f MB", float64(b)/(1<<20))
	}
	if b >= 1<<10 {
		return fmt.Sprintf("%.1f KB", float64(b)/(1<<10))
	}
	return fmt.Sprintf("%d B", b)
}
