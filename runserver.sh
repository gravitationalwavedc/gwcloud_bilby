#! /bin/bash
while ! nc -z db 3306; do
  sleep 1
done
/venv/bin/python /src/production-manage.py migrate
/venv/bin/gunicorn gw_bilby.wsgi --bind 0.0.0.0:8000 --workers 8 --timeout 600
