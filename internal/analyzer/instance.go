package analyzer

import (
	"github.com/asabla/meiliscan/internal/collector"
	"github.com/asabla/meiliscan/internal/finding"
)

// InstanceAnalyzer analyzes instance-level configuration.
type InstanceAnalyzer struct{}

// NewInstanceAnalyzer creates a new InstanceAnalyzer.
func NewInstanceAnalyzer() *InstanceAnalyzer {
	return &InstanceAnalyzer{}
}

// Name returns the analyzer name.
func (a *InstanceAnalyzer) Name() string {
	return "instance"
}

// Analyze runs instance configuration analysis on the collected data.
func (a *InstanceAnalyzer) Analyze(data *collector.CollectedData) []*finding.Finding {
	var findings []*finding.Finding

	// I001: No authentication (no master key)
	if f := a.checkNoAuthentication(data); f != nil {
		findings = append(findings, f)
	}

	return findings
}

// I001: No authentication (publicly accessible)
func (a *InstanceAnalyzer) checkNoAuthentication(data *collector.CollectedData) *finding.Finding {
	// Only applies to live instances
	if data.SourceType != "live" {
		return nil
	}

	// If we don't have instance info, we can't check
	if data.InstanceInfo == nil {
		return nil
	}

	// If no master key was provided but we could still access the API,
	// the instance is running without authentication
	if !data.InstanceInfo.HasMasterKey {
		return finding.New(
			"MEILI-I001",
			"Instance running without authentication",
			"The Meilisearch instance is accessible without any authentication. In production, all API routes (except /health) should be protected by a master key. Without authentication, anyone with network access can read, modify, or delete your data.",
			finding.SeverityCritical,
			finding.CategoryInstance,
		).WithRecommendation("Set a master key using the MEILI_MASTER_KEY environment variable or --master-key flag. The key should be at least 16 bytes for adequate security.").
			WithDetails(map[string]interface{}{
				"has_master_key": false,
				"instance_url":   data.SourceURL,
			})
	}

	return nil
}
