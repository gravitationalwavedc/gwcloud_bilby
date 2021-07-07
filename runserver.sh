#! /bin/bash
/src/venv/bin/python /src/production-manage.py migrate;
/src/venv/bin/python /src/production-manage.py collectstatic --noinput;

/src/venv/bin/gunicorn gw_bilby.wsgi --bind 0.0.0.0:8000 --workers 8 --timeout 600
