#!/bin/bash
# Assuming that you've tagged the built docker image with gwosc_ingest
# And created a sqlite.db file
# And created a .env file
source .env
# Ensure log file exists and is writable by the container (non-root) when bind-mounted
touch ./gwosc_ingest.log && chmod a+w ./gwosc_ingest.log
sudo docker run --env-file .env --network=host --mount type=bind,src="$HOST_DB_PATH",target="$DB_PATH" --mount type=bind,src="./gwosc_ingest.log",target="/gwosc_ingest.log" gwosc_ingest
