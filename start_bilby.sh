#!/bin/bash

cd ./src
mkdir -p docs/data
.venv/bin/python manage.py graphql_schema --settings=gw_bilby.dev
.venv/bin/python manage.py migrate --settings=gw_bilby.dev
.venv/bin/python manage.py runserver 8001 --settings=gw_bilby.dev
