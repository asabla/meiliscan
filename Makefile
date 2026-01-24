.PHONY: build test clean install run help snapshot release-dry-run

# Variables
BINARY_NAME=meiliscan
BUILD_DIR=.
GO_FILES=$(shell find . -name '*.go' -not -path './archive/*')

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@sed -n 's/^##//p' $(MAKEFILE_LIST) | column -t -s ':' | sed -e 's/^/ /'

## build: Build the binary
build:
	go build -o $(BINARY_NAME) ./cmd/meiliscan

## install: Install to GOPATH/bin
install:
	go install ./cmd/meiliscan

## test: Run all tests
test:
	go test ./...

## test-v: Run all tests with verbose output
test-v:
	go test -v ./...

## test-cover: Run tests with coverage
test-cover:
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

## lint: Run go vet
lint:
	go vet ./...

## fmt: Format code
fmt:
	go fmt ./...

## clean: Remove build artifacts
clean:
	rm -f $(BINARY_NAME)
	rm -f coverage.out coverage.html

## tidy: Tidy go modules
tidy:
	go mod tidy

## run: Build and run with sample args
run: build
	./$(BINARY_NAME) --help

## snapshot: Build snapshot release (for testing)
snapshot:
	goreleaser release --snapshot --clean

## release-dry-run: Test release process without publishing
release-dry-run:
	goreleaser release --skip=publish --clean
