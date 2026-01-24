package main

import (
	"os"

	"github.com/asabla/meiliscan/internal/cli"
)

func main() {
	if err := cli.Execute(); err != nil {
		os.Exit(1)
	}
}
