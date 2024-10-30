#!/bin/bash
# Assuming that you've tagged the built docker image with gwosc_ingest
# And created a sqlite.db file
# And created a .env file
source .env
docker run --env-file .env --mount type=bind,src="$HOST_DB_PATH",target="$DB_PATH" gwosc_ingest
