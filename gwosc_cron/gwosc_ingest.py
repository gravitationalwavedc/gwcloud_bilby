from gwcloud_python import GWCloud
import fcntl
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime
import h5py
import requests
from tempfile import NamedTemporaryFile
import logging
import sys

logger = logging.getLogger("gwosc_ingest")
logger.setLevel(logging.DEBUG)


fh = logging.FileHandler("gwosc_ingest.log")
fh.setLevel(logging.DEBUG)

sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.INFO)

logger.addHandler(fh)
logger.addHandler(sh)

try:
    from local import DB_PATH, GWCLOUD_TOKEN, AUTH_ENDPOINT, ENDPOINT
except ImportError:
    logger.info("No local.py file found, loading settings from env")
    GWCLOUD_TOKEN = os.getenv("GWCLOUD_TOKEN")
    ENDPOINT = os.getenv("ENDPOINT")
    DB_PATH = os.getenv("DB_PATH")

EVENTNAME_SEPERATOR = "--"
LOCK_FILE_PATH = str(Path(DB_PATH).with_suffix(".lock")) if DB_PATH else None
MAX_RETRY_ATTEMPTS = 24


def compute_is_latest_version(event_name, shared_common_names):
    """Return True if *event_name* is the latest-versioned name among *shared_common_names*.

    An unversioned name (no ``-vN`` suffix) is treated as v0, so it will be
    considered older than any explicitly versioned sibling.  If no name in the
    group carries a version suffix at all, every member is treated as v0 and
    all are considered equally "latest" (returns True).
    """
    if len(shared_common_names) <= 1:
        return True

    def _version(name):
        match = re.search(r"-v(\d+)$", name)
        # Unversioned names are treated as v0
        return int(match.group(1)) if match else 0

    current_version = _version(event_name)
    all_versions = [_version(name) for name in shared_common_names]
    return current_version == max(all_versions)


def fix_job_name(name):
    return re.sub("[^a-z0-9_-]", "-", name, flags=re.IGNORECASE)


def build_bilbyjob_name(event_name, config_name):
    return fix_job_name(f"{event_name}{EVENTNAME_SEPERATOR}{config_name}")


def create_table(cursor):
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS completed_jobs (job_id TEXT PRIMARY KEY, success BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reason TEXT, reason_data TEXT, catalog_shortname TEXT,common_name, all_succeeded INT, none_succeeded INT, is_latest_version BOOLEAN)"  # noqa
    )


def create_job_errors_table(cursor):
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS job_errors (job_id TEXT PRIMARY KEY, failure_count INTEGER NOT NULL DEFAULT 0, last_failure TIMESTAMP, last_error TEXT)"  # noqa
    )


def record_job_failure(con, cursor, job_id, error_msg):
    cursor.execute(
        "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, 1, CURRENT_TIMESTAMP, ?) "
        "ON CONFLICT(job_id) DO UPDATE SET failure_count = failure_count + 1, last_failure = CURRENT_TIMESTAMP, last_error = ?",
        (job_id, error_msg, error_msg),
    )
    con.commit()


def get_job_failure_count(cursor, job_id):
    row = cursor.execute("SELECT failure_count FROM job_errors WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return 0
    return row["failure_count"]


def check_and_download():
    logger.info(f"==== gwosc_ingest cronjob {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    create_table(cur)
    create_job_errors_table(cur)

    try:
        _check_and_download_inner(con, cur)
    finally:
        con.close()


def _check_and_download_inner(con, cur):
    def save_sqlite_job(
        job_id,
        common_name,
        catalog_shortname,
        success,
        reason,
        is_latest_version,
        reason_data="",
        all_succeeded=-1,
        none_succeeded=-1,
    ):
        cur.execute(
            "INSERT INTO completed_jobs (job_id, common_name, catalog_shortname, success, reason, is_latest_version, reason_data, all_succeeded, none_succeeded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                common_name,
                catalog_shortname,
                success,
                reason,
                is_latest_version,
                reason_data,
                all_succeeded,
                none_succeeded,
            ),
        )
        con.commit()

    gwc = GWCloud(GWCLOUD_TOKEN, endpoint=ENDPOINT)

    # Collect list of events from GWOSC
    r = requests.get("https://gwosc.org/eventapi/json/allevents", timeout=30)
    if r.status_code != 200:
        logger.critical(f"Unable to fetch allevents json (status: {r.status_code})")
        sys.exit(1)

    all_events = r.json()["events"]
    gwosc_events = [k for k in all_events.keys()]
    logger.info(f"GWOSC events found: {len(gwosc_events)}")

    # Collect list of events from GWCloud
    full_gwcloud_events = [n.name for n in gwc.get_official_job_list()]
    # Only those which follow the format EVENT_NAME--RUN_TYPE are considered to have a valid EVENT_NAME
    gwcloud_events = list(
        set(
            [
                fix_job_name(n.split(EVENTNAME_SEPERATOR)[0])
                for n in full_gwcloud_events
                if len(n.split(EVENTNAME_SEPERATOR)) > 1
            ]
        )
    )
    logger.info(f"GWCloud events found: {len(gwcloud_events)}")

    # fetch event_ids from gwcloud and turn them into a dict
    full_gwcloud_event_ids = gwc.get_all_event_ids()
    gwcloud_event_ids = {z.event_id: z for z in full_gwcloud_event_ids}

    # collect list of events from sqlite db
    sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
    sqlite_events = [j["job_id"] for j in sqlite_rows.fetchall()]

    logger.info(f"sqlite events found: {len(sqlite_events)}")
    logger.info(f"Potential bad runs found: {len(sqlite_events) - len(gwcloud_events)}")

    # Find non-matching dataset names
    jobs_delta = [j for j in gwosc_events if j not in sqlite_events]
    logger.info(f"Not matching events: {len(jobs_delta)}")

    if len(jobs_delta) == 0:
        logger.info("Nothing to do 😊")
        sys.exit(0)

    for event_name in jobs_delta:
        # Check if this event has exceeded the maximum retry attempts
        failure_count = get_job_failure_count(cur, event_name)
        if failure_count >= MAX_RETRY_ATTEMPTS:
            # Fetch last_error for reason_data
            err_row = cur.execute("SELECT last_error FROM job_errors WHERE job_id = ?", (event_name,)).fetchone()
            last_error = err_row["last_error"] if err_row else ""
            logger.error(f"{event_name} has failed {failure_count} times, marking as permanently failed")
            _broken_common_name = all_events[event_name].get("commonName", "")
            _broken_shared = [k for k, v in all_events.items() if v.get("commonName") == _broken_common_name]
            _broken_is_latest = compute_is_latest_version(event_name, _broken_shared)
            save_sqlite_job(
                event_name,
                _broken_common_name,
                all_events[event_name].get("catalog.shortName", ""),
                False,
                "max_retries_exceeded",
                _broken_is_latest,
                last_error,
            )
            continue

        logger.info(f"{event_name}: {all_events[event_name]['jsonurl']}")

        r = requests.get(all_events[event_name]["jsonurl"], timeout=30)
        if r.status_code != 200:
            error_msg = (
                f"Unable to fetch event json (status: {r.status_code}, event: "
                f"{event_name}, url: {all_events[event_name]['jsonurl']})"
            )
            logger.error(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue

        try:
            event_json = r.json()
        except Exception:
            error_msg = (
                f"Unable to parse event json (event: {event_name}, " f"url: {all_events[event_name]['jsonurl']})"
            )
            logger.error(error_msg, exc_info=True)
            record_job_failure(con, cur, event_name, error_msg)
            continue
        event_json = event_json["events"][event_name]
        parameters = event_json["parameters"]
        common_name = event_json["commonName"]
        catalog_shortname = event_json["catalog.shortName"]

        shared_common_names = [k for k, v in all_events.items() if v["commonName"] == common_name]
        is_latest_version = compute_is_latest_version(event_name, shared_common_names)

        gps = event_json["GPS"]
        gracedb_id = event_json["gracedb_id"]

        # Check if this should be skipped for being in the wrong type of catalog
        ignore_patterns = [
            "marginal",
            "preliminary",
            "initial_ligo_virgo",
        ]
        ignored = False
        for pattern in ignore_patterns:
            if re.search(pattern, catalog_shortname, flags=re.IGNORECASE):
                logger.error(
                    f"{event_name} ignored due to matching /{pattern}/ in catalog_shortname ({catalog_shortname})"
                )
                save_sqlite_job(
                    event_name,
                    common_name,
                    catalog_shortname,
                    False,
                    "ignored_event",
                    is_latest_version,
                    pattern,
                )
                ignored = True
                break
        if ignored:
            continue

        found = [v for v in parameters.values() if v["is_preferred"]]
        if len(found) != 1:
            logger.error(f"Unable to find preferred job for {event_name} 😠")
            save_sqlite_job(
                event_name,
                common_name,
                catalog_shortname,
                False,
                "no preferred job",
                is_latest_version,
            )
            continue

        h5url = found[0].get("data_url")
        if not h5url:
            logger.error(f"Preferred job for {event_name} does not contain a dataurl 😠")
            save_sqlite_job(event_name, common_name, catalog_shortname, False, "no dataurl", -1)
            continue

        # See if there is already an event_id for this event
        event_id = None
        if re.match(r"^GW\d{6}_\d{6}$", common_name):
            event_id = gwcloud_event_ids.get(common_name, None)
            if event_id is None:
                # we need to create one
                try:
                    event_id = gwc.create_event_id(common_name, gps, gracedb_id)
                    logger.info(f"Created a new event_id: {common_name}")
                except Exception:
                    error_msg = f"Failed to create event_id for {common_name}"
                    logger.error(error_msg, exc_info=True)
                    record_job_failure(con, cur, event_name, error_msg)
                    continue
            else:
                logger.info(f"event_id already found: {common_name}")
        else:
            logger.info(f"{common_name} is not a valid event_id, uploading job without one")

        logger.info("Downloading h5 file")
        logger.info(h5url)
        all_succeeded = True
        none_succeeded = True
        download_failed = False
        with NamedTemporaryFile(mode="rb+") as f:
            try:
                with requests.get(h5url, stream=True, timeout=(10, 300)) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            except Exception:
                error_msg = f"Downloading {h5url} failed 😠"
                logger.error(error_msg, exc_info=True)
                record_job_failure(con, cur, event_name, error_msg)
                download_failed = True

            if download_failed:
                continue

            logger.info("Download complete")

            # Load the h5 file, and read in the bilby ini file(s)
            try:
                h5_handle = h5py.File(f)
            except Exception:
                error_msg = f"Failed to open H5 file downloaded from {h5url}"
                logger.error(error_msg, exc_info=True)
                record_job_failure(con, cur, event_name, error_msg)
                continue
            h5_iteration_error = False
            with h5_handle as h5:
                logger.info(f"Found keys: {list(h5.keys())}")
                for toplevel_key in h5.keys():
                    try:
                        if not (
                            isinstance(h5[toplevel_key], h5py.Group)
                            and "config_file" in h5[toplevel_key]
                            and isinstance(h5[toplevel_key]["config_file"], h5py.Group)
                            and "config" in h5[toplevel_key]["config_file"]
                            and isinstance(h5[toplevel_key]["config_file"]["config"], h5py.Group)
                        ):
                            logger.info(f"config_file not found: {toplevel_key}")
                            continue

                        logger.info(f"config_file found: {toplevel_key}")
                        config = h5[toplevel_key]["config_file"]["config"]
                        ini_lines = []
                        for k in config.keys():
                            ini_lines.append(f"{k}={config[k][0].decode('utf-8')}")
                        ini_str = "\n".join(ini_lines)
                    except Exception:
                        error_msg = f"Failed to read H5 config data for key {toplevel_key!r} in {h5url}"
                        logger.error(error_msg, exc_info=True)
                        record_job_failure(con, cur, event_name, error_msg)
                        h5_iteration_error = True
                        break

                    try:
                        job = gwc.upload_external_job(
                            build_bilbyjob_name(event_name, toplevel_key),
                            toplevel_key,
                            False,
                            ini_str,
                            h5url,
                        )
                        logger.info(f"BilbyJob {job.id} created 😊")
                        if event_id is not None:
                            job.set_event_id(event_id)
                            logger.info(f" and set event_id to {event_id.event_id}")
                        else:
                            logger.info(" and has no event_id")
                        none_succeeded = False
                    except Exception:
                        all_succeeded = False
                        # we don't just raise here as we want to potentially upload other jobs
                        logger.error("Failed to create BilbyJob 😠", exc_info=True)

            if h5_iteration_error:
                continue

        # If we've iterated all the potential BilbyJobs, save the info to the sqlite database
        #
        # The job is considered successful if _all_ of the bilby configs found were able
        # to be successfully submitted, _and_ there was at least one job submitted.
        #
        # If the H5 had recognised configs but every single upload failed (none_succeeded
        # is still True and all_succeeded is False), that is a transient upload error —
        # record it for retry rather than permanently closing the event.
        #
        # Partial success (some uploaded, some failed) is accepted permanently: retrying
        # would hit duplicate-upload errors on the configs that already succeeded.
        if not all_succeeded and none_succeeded:
            error_msg = f"All BilbyJob uploads failed for {event_name} — will retry"
            logger.error(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
        else:
            save_sqlite_job(
                event_name,
                common_name,
                catalog_shortname,
                all_succeeded and not none_succeeded,
                "completed_submit",
                is_latest_version,
                "",
                all_succeeded,
                none_succeeded,
            )
        logger.info("Deleted temp h5 file")

        # One H5 processing attempt per invocation — whether the uploads succeeded,
        # partially failed, or all failed, we stop here so the cron job doesn't
        # consume too much time in a single pass.  Failed events remain in job_errors
        # and will be retried on the next run.
        break


def run():
    """Entry point that ensures only one instance runs at a time via an exclusive file lock.

    If another instance already holds the lock, logs a message and returns immediately.
    Exits with code 1 if DB_PATH is not configured.
    """
    if not DB_PATH:
        logger.critical("DB_PATH is not set — this is a misconfiguration. Exiting.")
        sys.exit(1)

    lock_fd = open(LOCK_FILE_PATH, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.info("Another instance is already running — skipping this run.")
        lock_fd.close()
        return

    try:
        check_and_download()
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    run()
