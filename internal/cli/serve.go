package cli

import (
	"fmt"

	"github.com/asabla/meiliscan/api"
	"github.com/spf13/cobra"
)

var (
	servePort int
	serveHost string
)

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Start the Meiliscan API server",
	Long: `Start the Meiliscan API server to analyze Meilisearch instances via HTTP.

The API provides endpoints for:
  - Health checks: GET /api/health
  - Analysis: POST /api/analyze
  - Streaming analysis: POST /api/analyze/stream (SSE)

Examples:
  # Start on default port 8080
  meiliscan serve

  # Start on a specific port
  meiliscan serve --port 3000

  # Bind to all interfaces
  meiliscan serve --host 0.0.0.0 --port 8080`,
	RunE: runServe,
}

func init() {
	rootCmd.AddCommand(serveCmd)

	serveCmd.Flags().IntVarP(&servePort, "port", "p", 8080, "Port to listen on")
	serveCmd.Flags().StringVarP(&serveHost, "host", "H", "127.0.0.1", "Host to bind to")
}

func runServe(cmd *cobra.Command, args []string) error {
	addr := fmt.Sprintf("%s:%d", serveHost, servePort)

	fmt.Printf("Meiliscan API Server\n")
	fmt.Printf("====================\n")
	fmt.Printf("Listening on: http://%s\n", addr)
	fmt.Printf("\n")
	fmt.Printf("Endpoints:\n")
	fmt.Printf("  GET  /api/health         - Health check\n")
	fmt.Printf("  POST /api/analyze        - Analyze instance\n")
	fmt.Printf("  POST /api/analyze/stream - Analyze with SSE progress\n")
	fmt.Printf("\n")
	fmt.Printf("Press Ctrl+C to stop\n")
	fmt.Printf("\n")

	server := api.NewServer()
	return server.ListenAndServe(addr)
}
