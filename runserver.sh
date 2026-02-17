#!/bin/bash
# Docker entrypoint for the Django app. Waits for MySQL, runs migrations, then
# starts Gunicorn. Expects to run with WORKDIR=/src; the database host must be
# reachable as "db" (or set DJANGO_DB_HOST / .env). Logs go to /var/log/gwcloud_bilby.
set -e

VENV=/src/.venv
PYTHON="$VENV/bin/python"
GUNICORN="$VENV/bin/gunicorn"

echo "Waiting for database (db:3306)..."
while ! nc -z db 3306; do
  sleep 1
done
echo "Database is up."

mkdir -p /var/log/gwcloud_bilby
"$PYTHON" /src/production-manage.py migrate
exec "$GUNICORN" gw_bilby.wsgi --bind 0.0.0.0:8000 --workers 8 --timeout 600
