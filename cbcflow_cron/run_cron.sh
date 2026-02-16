#!/bin/bash

# Run the cbcflow_ingest cron job in Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
SSH_KEY_PATH="${SSH_KEY_PATH:-/home/lewis/keys/ligo_gitlab.key}"
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
CBCFLOW_PATH="${CBCFLOW_PATH:-/home/lewis/Projects/cbcflow}"

# Create data directory if it doesn't exist
mkdir -p "$DATA_DIR/libraries"
mkdir -p "$DATA_DIR/sqlite_exports"

echo "Running cbcflow_ingest cron job..."
echo "SSH Key: $SSH_KEY_PATH"
echo "Data Directory: $DATA_DIR"
echo "cbcflow Path: $CBCFLOW_PATH"

# Run the Docker container
docker run --rm \
    -v "$SSH_KEY_PATH:/keys/ligo_gitlab.key:ro" \
    -v "$DATA_DIR:/data" \
    -v "$CBCFLOW_PATH:/cbcflow:ro" \
    -e GWCLOUD_TOKEN="${GWCLOUD_TOKEN}" \
    -e ENDPOINT="${ENDPOINT}" \
    -e DB_PATH="/data/cbcflow_ingest.db" \
    -e JOB_CONTROLLER_JWT_SECRET="${JOB_CONTROLLER_JWT_SECRET}" \
    -e JOB_CONTROLLER_API_URL="${JOB_CONTROLLER_API_URL:-https://jobcontroller.adacs.org.au/job/apiv1}" \
    -e SSH_KEY_PATH="/keys/ligo_gitlab.key" \
    -e LIBRARIES_DIR="/data/libraries" \
    -e SQLITE_DIR="/data/sqlite_exports" \
    cbcflow_ingest:latest

echo "Cron job complete!"
