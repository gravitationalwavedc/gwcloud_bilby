#!/bin/bash

cd ./src
mkdir -p docs/data
.venv/bin/python manage.py graphql_schema
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8001
