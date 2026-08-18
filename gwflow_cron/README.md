# gwflow_cron

Cron utilities and ingest service for GWFlow gravitational wave parameter estimation jobs.

The service mirrors the current GWFlow superevent set from cbcflow-portal into GWCloud, uploads current files through the job controller path, and maintains sqlite retry state for daily production operation.

For full production deployment, bootstrap procedures, token rotation, search index rebuilds, and operational recovery guidance, contact the project maintainers or refer to the project wiki.

## Install Dependencies

For local development and tests:

```bash
cd gwflow_cron/
poetry install
```

## Run Tests

```bash
cd gwflow_cron/
poetry run python -m coverage run -m xmlrunner discover -s tests -t . --output-file ./junit.xml
poetry run coverage report
```

## Build Docker Image

Production follows the GWOSC cron pattern and runs the ingest service from a Docker image:

```bash
cd gwflow_cron/
docker build -t gwflow_ingest .
```

## Configure Environment

Create a host-local `.env` from the example:

```bash
cd gwflow_cron/
cp .env.example .env
chmod 600 .env
```

Populate `.env` with production values for:

- `GWCLOUD_TOKEN`: API token for the GWFlow ingest user from `/auth/api-token`.
- `CBCFLOW_PORTAL_TOKEN` stores the cbcflow-portal service token from the portal deployment process.
- `JOB_CONTROLLER_JWT_SECRET`: the same job-controller secret used by Django.
- `JOB_CONTROLLER_BUNDLE`: the bundle value selected for GWFlow production.
- `DB_PATH` and `STAGING_DIR`: container paths used by the bind mounts.
- `HOST_DB_PATH` and `HOST_STAGING_PATH`: host paths for sqlite state and staging storage.
- `MAX_FILES_PER_RUN` and `MAX_BYTES_PER_RUN`: caps from the production capacity decision.

`run_cron.sh` uses `set -euo pipefail`; missing `DB_PATH`, `HOST_DB_PATH`, `STAGING_DIR`, or `HOST_STAGING_PATH` values will stop the wrapper before Docker runs. This is intentional so broken environment provisioning fails early.

Do not commit `.env`.

## Run Manually

Normal daily-style run:

```bash
cd gwflow_cron/
./run_cron.sh
```

Supervised bootstrap backfill:

```bash
cd gwflow_cron/
./run_cron.sh --backfill
```

`run_cron.sh` passes runtime arguments through to the container entrypoint, so the backfill flag reaches `gwflow_ingest.py`.

## Logs

The script bind-mounts `gwflow_ingest.log` into the container and writes it in the `gwflow_cron/` directory. In production, publish this log using the same nginx pattern as the existing GWOSC ingest log.

The log should show each run, transient failures, retry-cap exhaustion, authentication failures, and file mirror progress. Do not log token values or other secrets.

## Failure Handling

Common operational cases and their recovery procedures:

- **Job controller 503 or cluster offline**: treat as transient; the next daily run self-heals.
- **md5 mismatch**: source file changed mid-mirror; set `uploaded=False` on the affected file in Django admin and re-run.
- **Retry-cap exhaustion**: inspect `sqlite3 sqlite.db 'select * from job_errors order by updated_at desc;'`, fix the root cause, reset the row, re-run.
- **Portal token expiry (401s in log or UI)**: rotate `CBCFLOW_PORTAL_TOKEN` in both `gwflow_cron/.env` and the Django production environment, then restart Django.
- **Re-ingesting or re-mirroring a single superevent**: for metadata, run a supervised `./run_cron.sh`; for a specific file, set `uploaded=False` in Django admin.
