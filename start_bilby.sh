#!/bin/bash

cd ./src
mkdir -p docs/data
.venv/bin/python development-manage.py graphql_schema
.venv/bin/python development-manage.py migrate
.venv/bin/python development-manage.py runserver 8001
