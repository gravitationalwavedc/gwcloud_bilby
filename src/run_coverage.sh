#!/bin/bash
set -e
# Run Django tests with coverage; always use coverage's parallel mode so it
# works whether or not Django's --parallel is used. All arguments are passed
# straight through to manage.py test.
# Use from src/ with: bash run_coverage.sh [args]
# Examples:
#   ./run_coverage.sh
#   ./run_coverage.sh --failfast bilbyui.tests.test_models
#   ./run_coverage.sh --parallel 4

# Clean any old data, then always run in coverage's parallel mode. If Django
# isn't using --parallel you'll just get a single data file; if it is, each
# worker process will write its own, and combine will merge them.
export DJANGO_SETTINGS_MODULE=gw_bilby.test
poetry run python -m coverage erase
poetry run python -m coverage run --parallel-mode manage.py test "$@"
poetry run python -m coverage combine
poetry run python -m coverage report
