FROM python:3.12 as gwosc_ingest

# Update the container and install the required packages
RUN apt-get update
RUN apt-get -y install python3-dev build-essential curl

WORKDIR /

# Copy in the script
COPY gwosc_ingest.py gwosc_ingest.py
COPY requirements.txt requirements.txt

# Install requirements
RUN pip install --no-cache-dir -r /requirements.txt

ENTRYPOINT ["python", "gwosc_ingest.py"]
