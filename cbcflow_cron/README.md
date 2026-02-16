# CBC Workflow Library Ingest

This script ingests completed parameter estimation (PE) jobs from CBC workflow libraries into GWCloud.

## Overview

The CBC workflow libraries (e.g., cbc-workflow-o4a, cbc-workflow-o4c) contain metadata about gravitational wave parameter estimation analyses performed on the LIGO/Virgo/KAGRA data. This cron job:

1. **Clones/Updates Libraries**: Uses git with SSH authentication to clone or update CBC workflow repositories
2. **Exports to SQLite**: Uses cbcflow to export library metadata to SQLite databases for efficient querying
3. **Queries Completed Jobs**: Finds parameter estimation jobs with status="complete" and valid result files
4. **Downloads Result Files**: Downloads HDF5 result files from the CIT cluster using the job controller API
5. **Uploads to GWCloud**: Creates external Bilby jobs in GWCloud and stores result files in internal storage
6. **Tracks Progress**: Maintains a SQLite database to track which jobs have been processed

## Architecture

### Data Flow

```
CBC Workflow Git Repos → cbcflow SQLite Export → Query Completed PE Jobs
                                                          ↓
GWCloud Internal Storage ← Upload Job & Files ← Download from CIT Cluster
```

### File Storage

The script maintains several directories:

- `LIBRARIES_DIR`: Cloned git repositories
- `SQLITE_DIR`: Exported SQLite databases (kept for future sync operations)
- `DB_PATH`: Tracking database for processed jobs

**Important**: The SQLite export files are preserved between runs because they will be used in a future extension to upload these databases to a remote cluster.

### Job Naming Convention

Jobs are named using the format: `{sname}--{uid}`

Example: `S240525p--online` or `S231113bw--bilby-IMRPhenomXPHM-SpinTaylor`

## Configuration

### Environment Variables

If `local.py` is not present, the script reads from environment variables:

- `GWCLOUD_TOKEN`: Authentication token for GWCloud API
- `ENDPOINT`: GWCloud GraphQL endpoint
- `DB_PATH`: Path to tracking database (default: `./cbcflow_ingest.db`)
- `JOB_CONTROLLER_JWT_SECRET`: Secret for JWT authentication with job controller
- `JOB_CONTROLLER_API_URL`: Job controller API URL
- `SSH_KEY_PATH`: Path to SSH private key for LIGO GitLab
- `LIBRARIES_DIR`: Directory for cloned repositories (default: `./libraries`)
- `SQLITE_DIR`: Directory for SQLite exports (default: `./sqlite_exports`)

### Local Development

Copy `local.example-dev.py` to `local.py` and update with your settings:

```bash
cp local.example-dev.py local.py
# Edit local.py with your configuration
```

## Libraries Processed

The script processes three CBC workflow libraries:

1. **cbc-workflow-o4a**: O4a observing run
2. **cbc-workflow-o4c**: O4c observing run  
3. **cbc-workflow-er16-o4b**: Engineering run 16 and O4b

## Database Schema

### Tracking Database (`cbcflow_ingest.db`)

```sql
CREATE TABLE processed_jobs (
    job_uid TEXT PRIMARY KEY,           -- Unique job identifier from cbcflow
    sname TEXT,                         -- Superevent name (e.g., S240525p)
    library_name TEXT,                  -- Source library name
    success BOOLEAN,                    -- Whether processing succeeded
    timestamp TIMESTAMP,                -- When job was processed
    reason TEXT,                        -- Success/failure reason
    reason_data TEXT,                   -- Additional context
    gwcloud_job_id INTEGER              -- Created GWCloud job ID
);
```

### cbcflow SQLite Schema

The exported SQLite databases contain tables like:

- `superevents`: Main event information
- `superevents_parameterestimation`: PE configuration and status
- `superevents_parameterestimation_results`: Individual PE analysis results
- `linkedfiles`: File paths (result files, config files, etc.)

Key query to find completed PE jobs:

```sql
SELECT 
    s.sname,
    r.uid,
    lf.path as result_file_path
FROM superevents s
INNER JOIN superevents_parameterestimation pe ON s.id = pe.superevents_id
INNER JOIN superevents_parameterestimation_results r 
    ON pe.id = r.superevents_parameterestimation_id
LEFT JOIN linkedfiles lf ON r.resultfile_id = lf.id
WHERE r.runstatus = 'complete'
AND lf.path IS NOT NULL
AND r.deprecated = 0
```

## Running the Script

### Development

```bash
python cbcflow_ingest.py
```

### Production (Docker)

```bash
./build_docker.sh
./run_cron.sh
```

### Cron Schedule

The script is designed to run hourly:

```cron
0 * * * * /path/to/run_cron.sh
```

## Implementation Details

### File Downloads from CIT

The script downloads result files from the CIT cluster via HTTPS. Files in the CBC workflow libraries are stored in public_html directories and are accessible at:

```
https://ldas-jobs.ligo.caltech.edu/~<username>/<path>
```

For example:
- CIT path: `CIT:/home/pe.o4/public_html/O4b/S240525p/online/bilby/final_result/result.hdf5`
- HTTPS URL: `https://ldas-jobs.ligo.caltech.edu/~pe.o4/O4b/S240525p/online/bilby/final_result/result.hdf5`

**Note**: Currently, the script creates external jobs with direct links to the CIT cluster. File downloads are implemented but commented out to avoid storage overhead. Uncomment the download logic in `process_library()` to enable local file storage.

### Job Upload to GWCloud

Jobs are uploaded as "external" jobs:

- Type: `BilbyJobType.EXTERNAL`
- Marked as LIGO jobs (`is_ligo_job=True`)
- Result URL points to CIT cluster (or local storage if downloads enabled)
- Minimal ini string generated from available metadata
- Job names include library name to avoid conflicts: `{sname}--{uid}--{library}`

### Error Handling

The script is designed to be resilient:

- Git failures skip that library and continue
- SQLite export failures skip that library
- Individual job failures are logged but don't stop processing
- All errors logged to `cbcflow_ingest.log`

### Rate Limiting

To avoid overwhelming the system, the script:

- Processes only 1 new job per library per run
- Uses 30-minute JWT token expiry
- Has request timeouts (30s for API, 5min for file downloads)

## Logging

Two log outputs are configured:

1. **File**: `cbcflow_ingest.log` (DEBUG level, full details)
2. **Console**: stdout (INFO level, key events)

Log format includes:

- Timestamp
- Library being processed
- Jobs found/processed
- Success/failure status
- Detailed error traces

## Testing

See `test_cbcflow_ingest.py` for comprehensive test coverage:

- Git operations with SSH keys
- SQLite export and querying
- File downloads from job controller
- GWCloud job uploads
- Error handling and edge cases

Run tests:

```bash
python -m pytest test_cbcflow_ingest.py -v
```

## Future Enhancements

### SQLite Upload to Remote Cluster

The SQLite export files are preserved for a planned feature to upload them to a remote cluster for:

- Distributed analysis
- Backup/archival
- Cross-site collaboration

Implementation placeholder: Add upload logic after processing each library.

### Incremental Updates

Currently processes all completed jobs. Future versions could:

- Track last update time per library
- Only query for new/updated jobs
- Support differential updates

### Advanced File Management

- Verify MD5 checksums from linkedfiles table
- Support for multiple result file formats
- Batch file downloads for efficiency

## Troubleshooting

### Git Clone Failures

Check:
- SSH key permissions: `chmod 600 /path/to/key`
- SSH key is added to LIGO GitLab account
- Network connectivity to git.ligo.org

### SQLite Export Failures

- Ensure cbcflow is installed: `cbcflow_export_sqlite --version`
- Check library directory exists and has valid JSON files
- Look for cbcflow errors in stderr

### File Download Failures

- Verify `JOB_CONTROLLER_JWT_SECRET` is correct
- Check job controller API is accessible
- Ensure sufficient disk space for downloads

### GWCloud Upload Failures

- Verify `GWCLOUD_TOKEN` is valid
- Check API endpoint is accessible
- Review job name format (must be unique per user)

## Contact

For issues or questions about this cron job, contact the GWCloud development team.
