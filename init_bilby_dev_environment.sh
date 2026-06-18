echo Set up python virtual env for bilby module
cd "$(dirname "$0")/src" && poetry install
poetry run python development-manage.py migrate
