FROM python:3.12 as cbcflow_ingest

# Update the container and install required packages
RUN apt-get update && apt-get -y install \
    python3-dev \
    build-essential \
    curl \
    git \
    openssh-client

WORKDIR /app

# Install cbcflow first (from local directory - will be mounted)
# This is temporary until cbcflow is publicly accessible
# We install it as editable so we can mount the source
RUN pip install --upgrade pip

# Install requirements
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the script
COPY cbcflow_ingest.py cbcflow_ingest.py

# Create directories for data persistence
RUN mkdir -p /data/libraries /data/sqlite_exports /keys

# Set up SSH config to avoid host key verification issues
RUN mkdir -p /root/.ssh && \
    echo "Host git.ligo.org" > /root/.ssh/config && \
    echo "    StrictHostKeyChecking no" >> /root/.ssh/config && \
    echo "    UserKnownHostsFile=/dev/null" >> /root/.ssh/config

ENTRYPOINT ["python", "cbcflow_ingest.py"]
