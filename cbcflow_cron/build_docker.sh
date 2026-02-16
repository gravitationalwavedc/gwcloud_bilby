#!/bin/bash

# Build the Docker image for cbcflow_ingest

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building cbcflow_ingest Docker image..."

# Generate requirements.txt from requirements.in if needed
if [ -f "$SCRIPT_DIR/requirements.in" ]; then
    echo "Generating requirements.txt from requirements.in..."
    cd "$SCRIPT_DIR"
    pip-compile requirements.in
fi

# Build the Docker image
docker build -t cbcflow_ingest:latest -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"

echo "Build complete! Image: cbcflow_ingest:latest"
