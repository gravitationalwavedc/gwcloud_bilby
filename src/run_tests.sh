#!/bin/bash
set -e
# Run Django tests without coverage. All arguments are passed to manage.py test.
# Use from src/ with: poetry run bash run_tests.sh [args]
# Examples:
#   ./run_tests.sh
#   ./run_tests.sh --failfast
#   ./run_tests.sh bilbyui.tests.test_models
#   ./run_tests.sh --parallel 4
export DJANGO_SETTINGS_MODULE=gw_bilby.test
python manage.py test "$@"
