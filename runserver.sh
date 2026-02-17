#! /bin/bash
set -e
while ! nc -z db 3306; do
  sleep 1
done
mkdir -p /var/log/gwcloud_bilby
/venv/bin/python /src/production-manage.py migrate
/venv/bin/gunicorn gw_bilby.wsgi --bind 0.0.0.0:8000 --workers 8 --timeout 600
