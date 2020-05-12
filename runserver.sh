#! /bin/bash
/src/venv/bin/python /src/production-manage.py migrate;
/src/venv/bin/python /src/production-manage.py collectstatic --noinput;

gunicorn gw_bilby.wsgi -b 0.0.0.0:8000
