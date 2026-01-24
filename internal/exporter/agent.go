package exporter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

// AgentExporter exports reports in a format optimized for AI coding agents.
// The output is structured markdown with prioritized findings and actionable fix commands.
type AgentExporter struct {
	// IncludeAllFindings controls whether to include suggestion and info findings.
	// If false, only critical and warning findings are included.
	IncludeAllFindings bool

	// MaxFindings limits the number of findings to include (0 = no limit).
	MaxFindings int
}

// NewAgent creates a new AgentExporter with default settings.
func NewAgent() *AgentExporter {
	return &AgentExporter{
		IncludeAllFindings: true,
		MaxFindings:        0,
	}
}

// NewAgentWithOptions creates a new AgentExporter with custom options.
func NewAgentWithOptions(includeAll bool, maxFindings int) *AgentExporter {
	return &AgentExporter{
		IncludeAllFindings: includeAll,
		MaxFindings:        maxFindings,
	}
}

// Export converts the report to agent-friendly markdown.
func (e *AgentExporter) Export(r *report.Report) ([]byte, error) {
	var buf bytes.Buffer

	// Filter and limit findings
	findings := e.filterFindings(r.Findings)

	// Header
	buf.WriteString("# MeiliSearch Analysis Context\n\n")
	buf.WriteString("This document contains analysis results for your MeiliSearch instance.\n")
	buf.WriteString("Use this context to understand issues and apply fixes.\n\n")

	// Current state summary
	e.writeSummary(&buf, r, findings)

	// Group findings by severity
	criticals, warnings, suggestions, infos := groupBySeverity(findings)

	// Critical issues (always shown)
	if len(criticals) > 0 {
		e.writeFindingSection(&buf, "Critical Issues (Fix First)", criticals)
	}

	// Warnings (always shown)
	if len(warnings) > 0 {
		e.writeFindingSection(&buf, "Warnings (Should Address)", warnings)
	}

	// Suggestions (optional)
	if e.IncludeAllFindings && len(suggestions) > 0 {
		e.writeFindingSection(&buf, "Suggestions (Consider When Convenient)", suggestions)
	}

	// Info (optional)
	if e.IncludeAllFindings && len(infos) > 0 {
		e.writeFindingSection(&buf, "Informational Notes", infos)
	}

	// Quick fix script
	e.writeQuickFixScript(&buf, r, findings)

	// Index overview table
	e.writeIndexOverview(&buf, r, findings)

	return buf.Bytes(), nil
}

func (e *AgentExporter) filterFindings(findings []*finding.Finding) []*finding.Finding {
	var result []*finding.Finding

	for _, f := range findings {
		// Filter by severity if not including all
		if !e.IncludeAllFindings {
			if f.Severity != finding.SeverityCritical && f.Severity != finding.SeverityWarning {
				continue
			}
		}
		result = append(result, f)
	}

	// Apply max findings limit
	if e.MaxFindings > 0 && len(result) > e.MaxFindings {
		result = result[:e.MaxFindings]
	}

	return result
}

func (e *AgentExporter) writeSummary(buf *bytes.Buffer, r *report.Report, filtered []*finding.Finding) {
	buf.WriteString("## Current State Summary\n\n")

	// Instance info
	buf.WriteString(fmt.Sprintf("- **Instance:** %d indexes, %s documents, %s database\n",
		r.Instance.IndexCount,
		formatNumber(r.Instance.TotalDocuments),
		formatBytes(r.Instance.DatabaseSize)))

	// Health score with descriptive status
	healthDesc := describeHealthScore(r.Summary.HealthScore)
	buf.WriteString(fmt.Sprintf("- **Health Score:** %d/100 (%s)\n", r.Summary.HealthScore, healthDesc))

	// Issues found (from original counts, not filtered)
	buf.WriteString(fmt.Sprintf("- **Issues Found:** %d critical, %d warnings, %d suggestions, %d info\n",
		r.Summary.CriticalCount, r.Summary.WarningCount,
		r.Summary.SuggestionCount, r.Summary.InfoCount))

	// Source info
	if r.Source.URL != "" {
		buf.WriteString(fmt.Sprintf("- **URL:** `%s`\n", r.Source.URL))
	}
	if r.Instance.Version != "" {
		buf.WriteString(fmt.Sprintf("- **Version:** %s\n", r.Instance.Version))
	}

	// Show if findings were filtered/limited
	if len(filtered) < r.Summary.TotalFindings {
		buf.WriteString(fmt.Sprintf("- **Showing:** %d of %d findings\n", len(filtered), r.Summary.TotalFindings))
	}

	buf.WriteString("\n")
}

func (e *AgentExporter) writeFindingSection(buf *bytes.Buffer, title string, findings []*finding.Finding) {
	buf.WriteString(fmt.Sprintf("## %s\n\n", title))

	for _, f := range findings {
		buf.WriteString(fmt.Sprintf("### %s: %s\n\n", f.ID, f.Title))

		if f.IndexUID != "" {
			buf.WriteString(fmt.Sprintf("**Index:** `%s`\n\n", f.IndexUID))
		}

		buf.WriteString(fmt.Sprintf("**Problem:** %s\n\n", f.Description))

		// Show current configuration from details if available
		if f.Details != nil {
			if current, ok := extractCurrentConfig(f.Details); ok {
				buf.WriteString("**Current Configuration:**\n```json\n")
				buf.WriteString(current)
				buf.WriteString("\n```\n\n")
			}
		}

		if f.Recommendation != "" {
			buf.WriteString(fmt.Sprintf("**Recommended:** %s\n\n", f.Recommendation))
		}

		if f.FixCommand != "" {
			buf.WriteString("**Fix Command:**\n```bash\n")
			buf.WriteString(f.FixCommand)
			buf.WriteString("\n```\n\n")
		}

		buf.WriteString("---\n\n")
	}
}

func (e *AgentExporter) writeQuickFixScript(buf *bytes.Buffer, r *report.Report, findings []*finding.Finding) {
	// Collect all fix commands
	var fixes []fixEntry
	for _, f := range findings {
		if f.FixCommand != "" {
			fixes = append(fixes, fixEntry{
				ID:       f.ID,
				Title:    f.Title,
				Index:    f.IndexUID,
				Command:  f.FixCommand,
				Severity: f.Severity,
			})
		}
	}

	if len(fixes) == 0 {
		return
	}

	buf.WriteString("## Quick Fix Script\n\n")
	buf.WriteString("Run these commands to apply recommended fixes:\n\n")
	buf.WriteString("```bash\n")
	buf.WriteString("#!/bin/bash\n")
	buf.WriteString("# MeiliSearch Configuration Fix Script\n")
	buf.WriteString("# Generated by Meiliscan\n")
	buf.WriteString(fmt.Sprintf("# Analysis date: %s\n\n", r.GeneratedAt.Format("2006-01-02 15:04:05")))

	// Extract base URL from source
	baseURL := r.Source.URL
	if baseURL == "" {
		baseURL = "http://localhost:7700"
	}

	buf.WriteString(fmt.Sprintf("MEILISEARCH_URL=\"%s\"\n", baseURL))
	buf.WriteString("API_KEY=\"YOUR_API_KEY\"  # Replace with your API key\n\n")

	for _, fix := range fixes {
		buf.WriteString(fmt.Sprintf("# Fix: %s - %s\n", fix.ID, fix.Title))
		if fix.Index != "" {
			buf.WriteString(fmt.Sprintf("# Index: %s\n", fix.Index))
		}
		// Replace hardcoded URLs with variable
		cmd := strings.ReplaceAll(fix.Command, baseURL, "$MEILISEARCH_URL")
		buf.WriteString(cmd)
		buf.WriteString("\n\n")
	}

	buf.WriteString("echo 'Fixes applied!'\n")
	buf.WriteString("```\n\n")
}

func (e *AgentExporter) writeIndexOverview(buf *bytes.Buffer, r *report.Report, findings []*finding.Finding) {
	// Count findings per index
	indexFindings := make(map[string][]*finding.Finding)
	var globalFindings []*finding.Finding

	for _, f := range findings {
		if f.IndexUID == "" {
			globalFindings = append(globalFindings, f)
		} else {
			indexFindings[f.IndexUID] = append(indexFindings[f.IndexUID], f)
		}
	}

	// Skip if no index-specific findings
	if len(indexFindings) == 0 {
		return
	}

	buf.WriteString("## Index Overview\n\n")
	buf.WriteString("| Index | Findings | Top Issue |\n")
	buf.WriteString("|-------|----------|----------|\n")

	// Sort index names for consistent output
	var indexes []string
	for idx := range indexFindings {
		indexes = append(indexes, idx)
	}
	sort.Strings(indexes)

	for _, idx := range indexes {
		idxFindings := indexFindings[idx]
		topIssue := ""
		if len(idxFindings) > 0 {
			f := idxFindings[0] // Already sorted by severity
			topIssue = fmt.Sprintf("%s: %s", f.ID, truncate(f.Title, 40))
		}
		buf.WriteString(fmt.Sprintf("| `%s` | %d | %s |\n", idx, len(idxFindings), topIssue))
	}

	// Show global findings count if any
	if len(globalFindings) > 0 {
		topGlobal := globalFindings[0]
		buf.WriteString(fmt.Sprintf("| *(global)* | %d | %s: %s |\n",
			len(globalFindings), topGlobal.ID, truncate(topGlobal.Title, 40)))
	}

	buf.WriteString("\n")
}

// Helper types and functions

type fixEntry struct {
	ID       string
	Title    string
	Index    string
	Command  string
	Severity finding.Severity
}

func groupBySeverity(findings []*finding.Finding) (criticals, warnings, suggestions, infos []*finding.Finding) {
	for _, f := range findings {
		switch f.Severity {
		case finding.SeverityCritical:
			criticals = append(criticals, f)
		case finding.SeverityWarning:
			warnings = append(warnings, f)
		case finding.SeveritySuggestion:
			suggestions = append(suggestions, f)
		case finding.SeverityInfo:
			infos = append(infos, f)
		}
	}
	return
}

func describeHealthScore(score int) string {
	switch {
	case score >= 90:
		return "excellent"
	case score >= 70:
		return "good"
	case score >= 50:
		return "needs attention"
	case score >= 30:
		return "poor"
	default:
		return "critical"
	}
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

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

func extractCurrentConfig(details map[string]interface{}) (string, bool) {
	// Look for common config keys in details
	configKeys := []string{
		"searchable_attributes", "filterable_attributes", "sortable_attributes",
		"ranking_rules", "current_value", "current_config",
	}

	for _, key := range configKeys {
		if val, ok := details[key]; ok {
			jsonBytes, err := json.MarshalIndent(val, "", "  ")
			if err == nil {
				return string(jsonBytes), true
			}
		}
	}

	return "", false
}
