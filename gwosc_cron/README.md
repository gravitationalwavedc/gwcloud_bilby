# GWOSC Ingest

The purpose of this script is to ingest Bilby jobs from the GWOSC catalog into GWCloud. It is run every hour using cron.

## Log files

The logs for the ingest script can be publicly accessed at [https://gwcloud.org.au/gwosc_ingest/gwosc_ingest.log]. It details all runs of the scripts, including any potential failure states.

## Failures

The script can fail for the following reasons, which will be recorded in the log:

- Unable to fetch (usually a transient network issue)
- Ignored catalog (some catalogs are not ingested e.g., marginal)
- No preferred job (no job associated with the event is marked as 'preferred')
- No dataurl (the preferred job does not contain a valid URL to fetch data from)
- No config_file found (the h5 directory does not contain any valid Bilby jobs) *
- The config_file is invalid (error submitting to GWCloud)

\* Note that a single h5 file can contain multiple potential directories, one or more of which may contain a Bilby job.

A run of the ingest script is considered successful if at least one job is successfully uploaded to GWCloud, and also that all attempts to upload a Bilby job were successful.
