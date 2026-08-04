FROM python:3.12 AS gwflow_ingest

# Update the container and install the required packages
RUN apt-get update \
  && apt-get -y install python3-dev build-essential curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Poetry and project dependencies (production only)
RUN pip install --no-cache-dir poetry \
  && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./
RUN poetry install --without dev --no-interaction --no-root

# Copy in the modules
COPY settings.py state.py gwflow_ingest.py ./

ENTRYPOINT ["python", "gwflow_ingest.py"]
