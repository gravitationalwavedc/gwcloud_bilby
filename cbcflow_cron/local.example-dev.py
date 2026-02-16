"""
Local configuration example for cbcflow_ingest development.

Copy this file to local.py and update with your settings.
"""

# Path to SQLite database for tracking processed jobs
DB_PATH = "./cbcflow_ingest.db"

# GWCloud API configuration
GWCLOUD_TOKEN = "<your-gwcloud-token>"
ENDPOINT = "http://localhost:8000/graphql"

# Job Controller configuration
JOB_CONTROLLER_JWT_SECRET = "<your-jwt-secret>"
JOB_CONTROLLER_API_URL = "https://jobcontroller.adacs.org.au/job/apiv1"

# SSH key for accessing LIGO GitLab repositories
SSH_KEY_PATH = "/home/lewis/keys/ligo_gitlab.key"

# Directory to store cloned libraries
LIBRARIES_DIR = "./libraries"

# Directory to store SQLite exports
SQLITE_DIR = "./sqlite_exports"
