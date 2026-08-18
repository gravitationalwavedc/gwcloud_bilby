#!/bin/bash
set -euo pipefail

# GWFlow cron runner wrapper.
# Assuming that you've tagged the built docker image with gwflow_ingest,
# created a sqlite.db file, and created a .env file.
source .env

: "${HOST_DB_PATH:?HOST_DB_PATH must be set in .env}"
: "${DB_PATH:?DB_PATH must be set in .env}"
: "${HOST_STAGING_PATH:?HOST_STAGING_PATH must be set in .env}"
: "${STAGING_DIR:?STAGING_DIR must be set in .env}"

# Ensure log file exists and is writable by the container when bind-mounted.
touch ./gwflow_ingest.log && chmod a+w ./gwflow_ingest.log

sudo docker run --env-file .env --network=host \
  --mount type=bind,src="$HOST_DB_PATH",target="$DB_PATH" \
  --mount type=bind,src="$HOST_STAGING_PATH",target="$STAGING_DIR" \
  --mount type=bind,src="./gwflow_ingest.log",target="/app/gwflow_ingest.log" \
  gwflow_ingest "$@"
