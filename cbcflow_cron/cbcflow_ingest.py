"""
CBC Workflow Library Ingest

This script ingests completed parameter estimation jobs from CBC workflow libraries
into GWCloud. It performs the following tasks:

1. Clones/updates CBC workflow git repositories
2. Exports each library to SQLite using cbcflow
3. Queries for completed PE jobs with result files
4. Downloads result files from CIT cluster via job controller
5. Uploads jobs to GWCloud with result files stored internally

The script tracks processed jobs in a SQLite database to avoid duplicates.
"""

import datetime
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import jwt
import requests
from gwcloud_python import GWCloud

logger = logging.getLogger("cbcflow_ingest")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler("cbcflow_ingest.log")
fh.setLevel(logging.DEBUG)

sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.INFO)

logger.addHandler(fh)
logger.addHandler(sh)

# Try to load local configuration
try:
    from local import (
        DB_PATH,
        GWCLOUD_TOKEN,
        ENDPOINT,
        JOB_CONTROLLER_JWT_SECRET,
        JOB_CONTROLLER_API_URL,
        SSH_KEY_PATH,
        LIBRARIES_DIR,
        SQLITE_DIR,
    )
except ImportError:
    logger.info("No local.py file found, loading settings from env")
    GWCLOUD_TOKEN = os.getenv("GWCLOUD_TOKEN")
    ENDPOINT = os.getenv("ENDPOINT")
    DB_PATH = os.getenv("DB_PATH", "./cbcflow_ingest.db")
    JOB_CONTROLLER_JWT_SECRET = os.getenv("JOB_CONTROLLER_JWT_SECRET")
    JOB_CONTROLLER_API_URL = os.getenv(
        "JOB_CONTROLLER_API_URL", "https://jobcontroller.adacs.org.au/job/apiv1"
    )
    SSH_KEY_PATH = os.getenv("SSH_KEY_PATH", "/keys/ligo_gitlab.key")
    LIBRARIES_DIR = os.getenv("LIBRARIES_DIR", "./libraries")
    SQLITE_DIR = os.getenv("SQLITE_DIR", "./sqlite_exports")

# CBC workflow libraries to process
CBC_LIBRARIES = [
    {
        "name": "cbc-workflow-o4a",
        "url": "git@git.ligo.org:cbc/projects/cbc-workflow-o4a.git",
    },
    {
        "name": "cbc-workflow-o4c",
        "url": "git@git.ligo.org:cbc/projects/cbc-workflow-o4c.git",
    },
    {
        "name": "cbc-workflow-er16-o4b",
        "url": "git@git.ligo.org:cbc/projects/cbc-workflow-er16-o4b.git",
    },
]


def create_tracking_table(cursor):
    """Create the database table for tracking processed jobs."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_jobs (
            job_uid TEXT PRIMARY KEY,
            sname TEXT,
            library_name TEXT,
            success BOOLEAN,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            reason_data TEXT,
            gwcloud_job_id INTEGER
        )
        """
    )


def clone_or_update_repo(repo_url: str, repo_path: Path, ssh_key_path: str) -> bool:
    """
    Clone or update a git repository using SSH key authentication.
    
    Args:
        repo_url: Git repository URL
        repo_path: Local path where repo should be cloned
        ssh_key_path: Path to SSH private key
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Set up git SSH command
        git_ssh_cmd = f'ssh -i {ssh_key_path} -o StrictHostKeyChecking=no'
        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = git_ssh_cmd
        
        if repo_path.exists():
            logger.info(f"Updating existing repository at {repo_path}")
            subprocess.run(
                ["git", "pull"],
                cwd=repo_path,
                env=env,
                check=True,
                capture_output=True,
                text=True
            )
        else:
            logger.info(f"Cloning repository {repo_url} to {repo_path}")
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", repo_url, str(repo_path)],
                env=env,
                check=True,
                capture_output=True,
                text=True
            )
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e.stderr}")
        return False


def export_library_to_sqlite(library_path: Path, output_db: Path) -> bool:
    """
    Export a cbcflow library to SQLite database.
    
    Args:
        library_path: Path to the cbcflow library
        output_db: Path to output SQLite database
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Exporting {library_path} to {output_db}")
        
        # Use cbcflow_export_sqlite command
        result = subprocess.run(
            [
                "cbcflow_export_sqlite",
                "-o", str(output_db),
                "-l", str(library_path)
            ],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.debug(f"Export output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"SQLite export failed: {e.stderr}")
        return False


def query_completed_pe_jobs(sqlite_db: Path) -> List[Dict]:
    """
    Query for completed parameter estimation jobs with result files.
    
    Args:
        sqlite_db: Path to the SQLite database
        
    Returns:
        List of dictionaries containing job information
    """
    conn = sqlite3.connect(str(sqlite_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query for completed PE jobs with result files
    query = """
        SELECT 
            s.sname,
            r.uid,
            r.inferencesoftware,
            r.waveformapproximant,
            r.reviewstatus,
            r.runstatus,
            lf.path as result_file_path,
            lf.md5sum,
            cfg.path as config_file_path,
            pe.status as pe_status
        FROM superevents s
        INNER JOIN superevents_parameterestimation pe ON s.id = pe.superevents_id
        INNER JOIN superevents_parameterestimation_results r ON pe.id = r.superevents_parameterestimation_id
        LEFT JOIN linkedfiles lf ON r.resultfile_id = lf.id
        LEFT JOIN linkedfiles cfg ON r.configfile_id = cfg.id
        WHERE r.runstatus = 'complete'
        AND lf.path IS NOT NULL
        AND r.deprecated = 0
    """
    
    cursor.execute(query)
    jobs = []
    for row in cursor.fetchall():
        jobs.append(dict(row))
    
    conn.close()
    logger.info(f"Found {len(jobs)} completed PE jobs in database")
    return jobs


def download_file_from_cit(
    file_path: str,
    output_path: Path,
    use_https: bool = True
) -> bool:
    """
    Download a file from CIT cluster.
    
    The file_path should be in format "CIT:/path/to/file". Files on CIT are typically
    accessible via HTTPS at ldas-jobs.ligo.caltech.edu for public PE results.
    
    Args:
        file_path: Full file path (e.g., "CIT:/home/pe.o4/public_html/...")
        output_path: Local path to save the downloaded file
        use_https: If True, download via HTTPS from ldas-jobs.ligo.caltech.edu
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Parse the file path - remove "CIT:" prefix if present
        if file_path.startswith("CIT:"):
            remote_path = file_path[4:]
        else:
            remote_path = file_path
        
        if use_https:
            # Convert path to HTTPS URL
            # /home/pe.o4/public_html/... becomes https://ldas-jobs.ligo.caltech.edu/~pe.o4/...
            if "/home/" in remote_path and "/public_html/" in remote_path:
                # Extract username and path after public_html
                parts = remote_path.split("/home/", 1)[1]
                username = parts.split("/", 1)[0]
                path_after_public = parts.split("/public_html/", 1)[1] if "/public_html/" in parts else ""
                
                download_url = f"https://ldas-jobs.ligo.caltech.edu/~{username}/{path_after_public}"
            else:
                logger.error(f"Unable to convert CIT path to HTTPS URL: {remote_path}")
                return False
            
            logger.info(f"Downloading {remote_path} from {download_url}")
            
            with requests.get(download_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        else:
            # For files not in public_html, we would need a different method
            # This is a placeholder for future implementation
            logger.error(f"Direct CIT file access not implemented for non-public files: {remote_path}")
            return False
        
        logger.info(f"Successfully downloaded file to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}", exc_info=True)
        return False


def upload_job_to_gwcloud(
    gwc: GWCloud,
    job_info: Dict,
    library_name: str,
    downloaded_files_dir: Path
) -> Optional[int]:
    """
    Upload a PE job to GWCloud with result files.
    
    For CBC workflow jobs, we create an UPLOADED job type and store the downloaded
    result files in GWCloud's internal storage. The job will have the actual files
    rather than just referencing external URLs.
    
    Args:
        gwc: GWCloud API client
        job_info: Job information dictionary from sqlite query
        library_name: Name of the source library
        downloaded_files_dir: Directory containing downloaded result files
        
    Returns:
        GWCloud job ID if successful, None otherwise
    """
    try:
        # Generate a job name
        sname = job_info['sname']
        uid = job_info['uid']
        job_name = fix_job_name(f"{sname}--{uid}--{library_name}")
        
        # Create the bilby job directory structure
        job_dir = downloaded_files_dir / job_name
        job_dir.mkdir(exist_ok=True)
        
        # Create required subdirectories
        (job_dir / "data").mkdir(exist_ok=True)
        (job_dir / "result").mkdir(exist_ok=True)
        (job_dir / "results_page").mkdir(exist_ok=True)
        
        # Download and place the result file
        result_file_path = job_info.get('result_file_path')
        if result_file_path:
            result_file = job_dir / "result" / "result.hdf5"
            if not download_file_from_cit(result_file_path, result_file):
                logger.error(f"Failed to download result file for {job_name}")
                return None
        
        # Download and place the config file
        config_file_path = job_info.get('config_file_path')
        if not config_file_path:
            logger.warning(f"No config file available for job {job_name}, skipping")
            return None
            
        config_file = job_dir / f"{job_name}_config_complete.ini"
        if not download_file_from_cit(config_file_path, config_file):
            logger.error(f"Failed to download config file for {job_name}")
            return None
        
        logger.info(f"Uploading job {job_name} to GWCloud")
        
        # Upload the HDF5 job using the new HDF5 upload functionality
        hdf5_file = job_dir / "result" / "result.hdf5"
        ini_file = job_dir / f"{job_name}_config_complete.ini"
        
        job = gwc.upload_hdf5_job(
            description=f"CBC Workflow PE job from {library_name} - {sname} - Review: {job_info.get('reviewstatus', 'N/A')}",
            hdf5_file=str(hdf5_file),
            ini_file=str(ini_file),
            public=True
        )
        
        logger.info(f"Successfully created GWCloud job {job.id}")
        
        return job.id
        
    except Exception as e:
        logger.error(f"Error uploading job to GWCloud: {e}", exc_info=True)
        return None


def fix_job_name(name: str) -> str:
    """Fix job name to be valid for GWCloud."""
    return re.sub("[^a-z0-9_-]", "-", name, flags=re.IGNORECASE)


def process_library(
    library_config: Dict,
    gwc: GWCloud,
    tracking_cursor: sqlite3.Cursor,
    tracking_conn: sqlite3.Connection
) -> Tuple[int, int]:
    """
    Process a single CBC workflow library.
    
    Args:
        library_config: Library configuration dictionary
        gwc: GWCloud API client
        tracking_cursor: Database cursor for tracking
        tracking_conn: Database connection for tracking
        
    Returns:
        Tuple of (successful_jobs, failed_jobs)
    """
    library_name = library_config["name"]
    library_url = library_config["url"]
    
    logger.info(f"Processing library: {library_name}")
    
    # Set up paths
    libraries_dir = Path(LIBRARIES_DIR)
    sqlite_dir = Path(SQLITE_DIR)
    libraries_dir.mkdir(parents=True, exist_ok=True)
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    
    library_path = libraries_dir / library_name
    sqlite_db = sqlite_dir / f"{library_name}.db"
    
    # Clone or update repository
    if not clone_or_update_repo(library_url, library_path, SSH_KEY_PATH):
        logger.error(f"Failed to clone/update {library_name}")
        return 0, 0
    
    # Export to SQLite
    if not export_library_to_sqlite(library_path, sqlite_db):
        logger.error(f"Failed to export {library_name} to SQLite")
        return 0, 0
    
    # Query for completed jobs
    completed_jobs = query_completed_pe_jobs(sqlite_db)
    
    # Filter out already processed jobs
    new_jobs = []
    for job in completed_jobs:
        tracking_cursor.execute(
            "SELECT job_uid FROM processed_jobs WHERE job_uid = ?",
            (job['uid'],)
        )
        if not tracking_cursor.fetchone():
            new_jobs.append(job)
    
    logger.info(f"Found {len(new_jobs)} new jobs to process")
    
    successful = 0
    failed = 0
    
    # Process each new job (limit to 1 per run for now to avoid overwhelming the system)
    for job in new_jobs[:1]:
        logger.info(f"Processing job {job['uid']} from {job['sname']}")
        
        # Create a temporary directory for downloaded files
        temp_dir = Path(tempfile.mkdtemp(prefix=f"cbcflow_{job['uid']}_"))
        
        try:
            # Upload the job to GWCloud (this will download files internally)
            job_id = upload_job_to_gwcloud(gwc, job, library_name, temp_dir)
            
            if job_id:
                successful += 1
                tracking_cursor.execute(
                    """
                    INSERT INTO processed_jobs 
                    (job_uid, sname, library_name, success, reason, gwcloud_job_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (job['uid'], job['sname'], library_name, True, "completed", job_id)
                )
            else:
                failed += 1
                tracking_cursor.execute(
                    """
                    INSERT INTO processed_jobs 
                    (job_uid, sname, library_name, success, reason)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (job['uid'], job['sname'], library_name, False, "upload_failed")
                )
            
            tracking_conn.commit()
        finally:
            # Clean up temporary directory
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    return successful, failed


def main():
    """Main entry point for the cron job."""
    logger.info(
        f"==== cbcflow_ingest cronjob {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===="
    )
    
    # Connect to tracking database
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    create_tracking_table(cur)
    con.commit()
    
    # Initialize GWCloud client
    gwc = GWCloud(GWCLOUD_TOKEN, endpoint=ENDPOINT)
    
    total_successful = 0
    total_failed = 0
    
    # Process each library
    for library_config in CBC_LIBRARIES:
        successful, failed = process_library(library_config, gwc, cur, con)
        total_successful += successful
        total_failed += failed
    
    logger.info(
        f"Processing complete: {total_successful} successful, {total_failed} failed"
    )
    
    con.close()


if __name__ == "__main__":
    main()
