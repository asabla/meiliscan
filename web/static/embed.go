// Package static embeds the web static files.
package static

import "embed"

//go:embed style.css htmx.min.js
var Files embed.FS
