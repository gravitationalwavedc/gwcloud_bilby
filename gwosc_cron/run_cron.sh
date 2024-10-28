#!/bin/bash
# Assuming that you've tagged the built docker image with gwosc_ingest
# And created a sqlite.db file
# And created a .env file
docker run --env-file .env --mount type=bind,src="$(pwd)"/sqlite.db,target=/sqlite.db gwosc_ingest
