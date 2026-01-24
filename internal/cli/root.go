// Package cli provides the command-line interface for meiliscan.
package cli

import (
	"github.com/spf13/cobra"
)

var (
	// Version is set at build time
	Version = "dev"
)

var rootCmd = &cobra.Command{
	Use:   "meiliscan",
	Short: "Analyze Meilisearch instances and dump files",
	Long: `Meiliscan is a comprehensive tool for analyzing Meilisearch instances
and dump files to identify optimization opportunities, potential pitfalls,
and provide actionable recommendations.

Examples:
  # Analyze a live instance
  meiliscan analyze --url http://localhost:7700

  # Analyze with API key
  meiliscan analyze --url http://localhost:7700 --api-key your-master-key

  # Save results to file
  meiliscan analyze --url http://localhost:7700 --output analysis.json`,
}

func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.Version = Version
}
