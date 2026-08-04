#!/bin/bash
# Assuming that you've tagged the built docker image with gwflow_ingest
# And created a sqlite.db file
# And created a .env file
source .env
# Ensure log file exists and is writable by the container (non-root) when bind-mounted
touch ./gwflow_ingest.log && chmod a+w ./gwflow_ingest.log
sudo docker run --env-file .env --network=host \
  --mount type=bind,src="$HOST_DB_PATH",target="$DB_PATH" \
  --mount type=bind,src="$HOST_STAGING_PATH",target="$STAGING_DIR" \
  --mount type=bind,src="./gwflow_ingest.log",target="/app/gwflow_ingest.log" \
  gwflow_ingest
