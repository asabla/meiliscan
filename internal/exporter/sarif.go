package exporter

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/asabla/meiliscan/internal/finding"
	"github.com/asabla/meiliscan/internal/report"
)

// SARIFExporter exports reports in SARIF format for CI/CD integration.
// SARIF (Static Analysis Results Interchange Format) is a standard format
// supported by GitHub, GitLab, Azure DevOps, and other CI platforms.
type SARIFExporter struct{}

// NewSARIF creates a new SARIFExporter.
func NewSARIF() *SARIFExporter {
	return &SARIFExporter{}
}

// SARIF format structures based on SARIF 2.1.0 specification
// https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html

// sarifLog is the root object of a SARIF document.
type sarifLog struct {
	Schema  string     `json:"$schema"`
	Version string     `json:"version"`
	Runs    []sarifRun `json:"runs"`
}

// sarifRun represents a single run of an analysis tool.
type sarifRun struct {
	Tool        sarifTool         `json:"tool"`
	Results     []sarifResult     `json:"results"`
	Invocations []sarifInvocation `json:"invocations,omitempty"`
	Artifacts   []sarifArtifact   `json:"artifacts,omitempty"`
}

// sarifTool describes the analysis tool.
type sarifTool struct {
	Driver sarifDriver `json:"driver"`
}

// sarifDriver provides information about the tool itself.
type sarifDriver struct {
	Name           string      `json:"name"`
	Version        string      `json:"version,omitempty"`
	InformationURI string      `json:"informationUri,omitempty"`
	Rules          []sarifRule `json:"rules,omitempty"`
}

// sarifRule describes a rule used by the tool.
type sarifRule struct {
	ID                   string                 `json:"id"`
	Name                 string                 `json:"name,omitempty"`
	ShortDescription     sarifMessage           `json:"shortDescription,omitempty"`
	FullDescription      sarifMessage           `json:"fullDescription,omitempty"`
	HelpURI              string                 `json:"helpUri,omitempty"`
	DefaultConfiguration sarifConfiguration     `json:"defaultConfiguration,omitempty"`
	Properties           map[string]interface{} `json:"properties,omitempty"`
}

// sarifConfiguration describes the default configuration for a rule.
type sarifConfiguration struct {
	Level string `json:"level,omitempty"`
}

// sarifResult represents a single finding/result.
type sarifResult struct {
	RuleID     string                 `json:"ruleId"`
	Level      string                 `json:"level"`
	Message    sarifMessage           `json:"message"`
	Locations  []sarifLocation        `json:"locations,omitempty"`
	Properties map[string]interface{} `json:"properties,omitempty"`
	Fixes      []sarifFix             `json:"fixes,omitempty"`
}

// sarifMessage contains a message.
type sarifMessage struct {
	Text     string `json:"text,omitempty"`
	Markdown string `json:"markdown,omitempty"`
}

// sarifLocation describes a location in an artifact.
type sarifLocation struct {
	PhysicalLocation *sarifPhysicalLocation `json:"physicalLocation,omitempty"`
	LogicalLocations []sarifLogicalLocation `json:"logicalLocations,omitempty"`
}

// sarifPhysicalLocation describes a physical location.
type sarifPhysicalLocation struct {
	ArtifactLocation sarifArtifactLocation `json:"artifactLocation,omitempty"`
	Region           *sarifRegion          `json:"region,omitempty"`
}

// sarifArtifactLocation describes the location of an artifact.
type sarifArtifactLocation struct {
	URI   string `json:"uri,omitempty"`
	Index int    `json:"index,omitempty"`
}

// sarifRegion describes a region within an artifact.
type sarifRegion struct {
	StartLine   int `json:"startLine,omitempty"`
	StartColumn int `json:"startColumn,omitempty"`
	EndLine     int `json:"endLine,omitempty"`
	EndColumn   int `json:"endColumn,omitempty"`
}

// sarifLogicalLocation describes a logical location (e.g., index name).
type sarifLogicalLocation struct {
	Name               string `json:"name,omitempty"`
	FullyQualifiedName string `json:"fullyQualifiedName,omitempty"`
	Kind               string `json:"kind,omitempty"`
}

// sarifArtifact describes an artifact analyzed by the tool.
type sarifArtifact struct {
	Location sarifArtifactLocation `json:"location"`
	MimeType string                `json:"mimeType,omitempty"`
}

// sarifInvocation describes a single invocation of the tool.
type sarifInvocation struct {
	ExecutionSuccessful bool   `json:"executionSuccessful"`
	StartTimeUTC        string `json:"startTimeUtc,omitempty"`
	EndTimeUTC          string `json:"endTimeUtc,omitempty"`
}

// sarifFix describes a proposed fix.
type sarifFix struct {
	Description sarifMessage `json:"description,omitempty"`
}

// Export converts the report to SARIF format.
func (e *SARIFExporter) Export(r *report.Report) ([]byte, error) {
	sarif := e.buildSARIF(r)
	return json.MarshalIndent(sarif, "", "  ")
}

// buildSARIF constructs the SARIF log from the report.
func (e *SARIFExporter) buildSARIF(r *report.Report) *sarifLog {
	// Build rules from unique finding IDs
	rulesMap := make(map[string]sarifRule)
	for _, f := range r.Findings {
		if _, ok := rulesMap[f.ID]; !ok {
			rulesMap[f.ID] = e.buildRule(f)
		}
	}
	rules := make([]sarifRule, 0, len(rulesMap))
	for _, rule := range rulesMap {
		rules = append(rules, rule)
	}

	// Build results
	results := make([]sarifResult, 0, len(r.Findings))
	for _, f := range r.Findings {
		results = append(results, e.buildResult(f))
	}

	return &sarifLog{
		Schema:  "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
		Version: "2.1.0",
		Runs: []sarifRun{
			{
				Tool: sarifTool{
					Driver: sarifDriver{
						Name:           "meiliscan",
						Version:        "1.0.0",
						InformationURI: "https://github.com/asabla/meiliscan",
						Rules:          rules,
					},
				},
				Results: results,
				Invocations: []sarifInvocation{
					{
						ExecutionSuccessful: true,
						StartTimeUTC:        r.GeneratedAt.UTC().Format(time.RFC3339),
						EndTimeUTC:          time.Now().UTC().Format(time.RFC3339),
					},
				},
			},
		},
	}
}

// buildRule creates a SARIF rule from a finding.
func (e *SARIFExporter) buildRule(f *finding.Finding) sarifRule {
	rule := sarifRule{
		ID:   f.ID,
		Name: f.Title,
		ShortDescription: sarifMessage{
			Text: f.Title,
		},
		FullDescription: sarifMessage{
			Text: f.Description,
		},
		DefaultConfiguration: sarifConfiguration{
			Level: e.severityToLevel(f.Severity),
		},
		Properties: map[string]interface{}{
			"category": string(f.Category),
		},
	}

	// Add help URI based on category
	rule.HelpURI = fmt.Sprintf("https://github.com/asabla/meiliscan#%s", f.ID)

	return rule
}

// buildResult creates a SARIF result from a finding.
func (e *SARIFExporter) buildResult(f *finding.Finding) sarifResult {
	result := sarifResult{
		RuleID: f.ID,
		Level:  e.severityToLevel(f.Severity),
		Message: sarifMessage{
			Text: f.Description,
		},
		Properties: map[string]interface{}{
			"category": string(f.Category),
		},
	}

	// Add logical location if index-specific
	if f.IndexUID != "" {
		result.Locations = []sarifLocation{
			{
				LogicalLocations: []sarifLogicalLocation{
					{
						Name:               f.IndexUID,
						FullyQualifiedName: fmt.Sprintf("index/%s", f.IndexUID),
						Kind:               "index",
					},
				},
			},
		}
	}

	// Add recommendation as fix if available
	if f.Recommendation != "" {
		result.Fixes = []sarifFix{
			{
				Description: sarifMessage{
					Text: f.Recommendation,
				},
			},
		}
	}

	// Add details to properties
	if len(f.Details) > 0 {
		result.Properties["details"] = f.Details
	}

	return result
}

// severityToLevel converts a finding severity to SARIF level.
// SARIF levels: error, warning, note, none
func (e *SARIFExporter) severityToLevel(s finding.Severity) string {
	switch s {
	case finding.SeverityCritical:
		return "error"
	case finding.SeverityWarning:
		return "warning"
	case finding.SeveritySuggestion:
		return "note"
	case finding.SeverityInfo:
		return "note"
	default:
		return "none"
	}
}
