import fcntl
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import h5py
import requests
from gwcloud_python import GWCloud
from gwdc_python.exceptions import GWDCUnknownException

logger = logging.getLogger("gwosc_ingest")
logger.setLevel(logging.DEBUG)


if not logger.handlers:
    fh = logging.FileHandler("gwosc_ingest.log")
    fh.setLevel(logging.DEBUG)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(sh)

try:
    from local import DB_PATH, ENDPOINT, GWCLOUD_TOKEN
except ImportError:
    logger.info("No local.py file found, loading settings from env")
    GWCLOUD_TOKEN = os.getenv("GWCLOUD_TOKEN")
    ENDPOINT = os.getenv("ENDPOINT")
    DB_PATH = os.getenv("DB_PATH")

EVENTNAME_SEPARATOR = "--"
LOCK_FILE_PATH = str(Path(DB_PATH).with_suffix(".lock")) if DB_PATH else None
MAX_RETRY_ATTEMPTS = 24

_VERSION_RE = re.compile(r"-v(\d+)$")
_JOB_NAME_RE = re.compile(r"[^a-z0-9_-]", re.IGNORECASE)
_EVENT_ID_RE = re.compile(r"^GW\d{6}_\d{6}$")


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
        match = _VERSION_RE.search(name)
        # Unversioned names are treated as v0
        return int(match.group(1)) if match else 0

    current_version = _version(event_name)
    all_versions = [_version(name) for name in shared_common_names]
    return current_version == max(all_versions)


def _is_latest_version(event_name, all_events, common_name):
    """Return True if *event_name* is the latest-versioned event sharing *common_name*.

    Collects every event in *all_events* that shares the same common name, then
    delegates the version comparison to :func:`compute_is_latest_version`.
    """
    shared_common_names = [
        k for k, v in all_events.items() if isinstance(v, dict) and v.get("commonName") == common_name
    ]
    return compute_is_latest_version(event_name, shared_common_names)


def fix_job_name(name):
    """Sanitize a string for use as a BilbyJob name.

    Replaces any character that is not alphanumeric, ``_``, or ``-`` with a
    hyphen so the result is safe for use in URLs and file paths.
    """
    return _JOB_NAME_RE.sub("-", name)


def build_bilbyjob_name(event_name, config_name):
    """Construct a BilbyJob name from an event name and a config name.

    Joins *event_name* and *config_name* with ``--`` then sanitises the
    result via :func:`fix_job_name` so it is safe for use as a job identifier.
    """
    return fix_job_name(f"{event_name}{EVENTNAME_SEPARATOR}{config_name}")


def create_table(cursor):
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS completed_jobs (job_id TEXT PRIMARY KEY, success BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reason TEXT, reason_data TEXT, catalog_shortname TEXT, common_name TEXT, all_succeeded INT, none_succeeded INT, is_latest_version BOOLEAN)"
    )


def create_job_errors_table(cursor):
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS job_errors (job_id TEXT PRIMARY KEY, failure_count INTEGER NOT NULL DEFAULT 0, last_failure TIMESTAMP, last_error TEXT)"
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
    logger.info("==== gwosc_ingest cronjob %s ====", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
    try:
        r = requests.get("https://gwosc.org/eventapi/json/allevents", timeout=30)
    except requests.RequestException:
        logger.critical("Unable to fetch allevents json (network error)")
        sys.exit(1)
    if r.status_code != 200:
        logger.critical(f"Unable to fetch allevents json (status: {r.status_code})")
        sys.exit(1)

    allevents_payload = r.json()
    if not isinstance(allevents_payload, dict):
        all_events = {}
    else:
        events = allevents_payload.get("events")
        all_events = events if isinstance(events, dict) else {}
    gwosc_events = list(all_events)
    logger.info("GWOSC events found: %s", len(gwosc_events))

    # Collect list of events from GWCloud
    full_gwcloud_events = [n.name for n in gwc.get_official_job_list()]
    # Only those which follow the format EVENT_NAME--RUN_TYPE are considered to have a valid EVENT_NAME
    gwcloud_events = {
        fix_job_name(n.split(EVENTNAME_SEPARATOR)[0]) for n in full_gwcloud_events if EVENTNAME_SEPARATOR in n
    }
    logger.info("GWCloud events found: %s", len(gwcloud_events))

    # fetch event_ids from gwcloud and turn them into a dict
    full_gwcloud_event_ids = gwc.get_all_event_ids()
    gwcloud_event_ids = {z.event_id: z for z in full_gwcloud_event_ids}

    # collect list of events from sqlite db
    sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
    sqlite_events = [j["job_id"] for j in sqlite_rows.fetchall()]

    logger.info("sqlite events found: %s", len(sqlite_events))
    logger.info("Potential bad runs found: %s", len(sqlite_events) - len(gwcloud_events))

    # Find non-matching dataset names
    jobs_delta = [j for j in gwosc_events if j not in sqlite_events]
    logger.info("Not matching events: %s", len(jobs_delta))

    if not jobs_delta:
        logger.info("Nothing to do 😊")
        sys.exit(0)

    for event_name in jobs_delta:
        event_data = all_events[event_name]
        # Check if this event has exceeded the maximum retry attempts
        failure_count = get_job_failure_count(cur, event_name)
        if failure_count >= MAX_RETRY_ATTEMPTS:
            # Fetch last_error for reason_data
            err_row = cur.execute("SELECT last_error FROM job_errors WHERE job_id = ?", (event_name,)).fetchone()
            last_error = err_row["last_error"] if err_row else ""
            logger.error("%s has failed %s times, marking as permanently failed", event_name, failure_count)
            common_name = event_data.get("commonName", "") if isinstance(event_data, dict) else ""
            is_latest_version = _is_latest_version(event_name, all_events, common_name)
            save_sqlite_job(
                event_name,
                common_name,
                event_data.get("catalog.shortName", "") if isinstance(event_data, dict) else "",
                False,
                "max_retries_exceeded",
                is_latest_version,
                last_error,
            )
            continue

        jsonurl = event_data.get("jsonurl") if isinstance(event_data, dict) else None
        if jsonurl is None:
            error_msg = f"Event {event_name} has no jsonurl in allevents payload"
            logger.error(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue

        logger.info("%s: %s", event_name, jsonurl)

        try:
            r = requests.get(jsonurl, timeout=30)
        except requests.RequestException:
            error_msg = f"Unable to fetch event json (event: {event_name}, url: {jsonurl})"
            logger.exception(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue

        if r.status_code != 200:
            error_msg = f"Unable to fetch event json (status: {r.status_code}, event: {event_name}, url: {jsonurl})"
            logger.error(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue

        try:
            event_json = r.json()
        except ValueError:
            error_msg = f"Unable to parse event json (event: {event_name}, url: {jsonurl})"
            logger.exception(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue
        try:
            event_json = event_json["events"][event_name]
            parameters = event_json["parameters"]
            common_name = event_json["commonName"] or ""
            catalog_shortname = event_json["catalog.shortName"] or ""
            gps = event_json["GPS"]
            gracedb_id = event_json["gracedb_id"]
        except (KeyError, TypeError):
            error_msg = f"Event {event_name} json payload is missing expected keys"
            logger.exception(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue

        if not isinstance(parameters, dict):
            error_msg = f"Event {event_name} json payload has a non-dict parameters section"
            logger.error(error_msg)
            record_job_failure(con, cur, event_name, error_msg)
            continue

        is_latest_version = _is_latest_version(event_name, all_events, common_name)

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

        found = [v for v in parameters.values() if isinstance(v, dict) and v.get("is_preferred")]
        if len(found) != 1:
            logger.error("Unable to find preferred job for %s 😠", event_name)
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
            logger.error("Preferred job for %s does not contain a dataurl 😠", event_name)
            save_sqlite_job(event_name, common_name, catalog_shortname, False, "no dataurl", is_latest_version)
            continue

        # See if there is already an event_id for this event
        event_id = None
        if _EVENT_ID_RE.match(common_name):
            event_id = gwcloud_event_ids.get(common_name)
            if event_id is None:
                # we need to create one
                try:
                    event_id = gwc.create_event_id(common_name, gps, gracedb_id)
                    logger.info("Created a new event_id: %s", common_name)
                except GWDCUnknownException:
                    error_msg = f"Failed to create event_id for {common_name}"
                    logger.exception(error_msg)
                    record_job_failure(con, cur, event_name, error_msg)
                    continue
            else:
                logger.info("event_id already found: %s", common_name)
        else:
            logger.info("%s is not a valid event_id, uploading job without one", common_name)

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
            except requests.RequestException:
                error_msg = f"Downloading {h5url} failed 😠"
                logger.exception(error_msg)
                record_job_failure(con, cur, event_name, error_msg)
                download_failed = True

            if download_failed:
                continue

            logger.info("Download complete")

            # Load the h5 file, and read in the bilby ini file(s)
            try:
                h5_handle = h5py.File(f)
            except OSError:
                error_msg = f"Failed to open H5 file downloaded from {h5url}"
                logger.exception(error_msg)
                record_job_failure(con, cur, event_name, error_msg)
                continue
            h5_iteration_error = False
            with h5_handle as h5:
                logger.info("Found keys: %s", list(h5.keys()))
                for toplevel_key in h5:
                    try:
                        if not (
                            isinstance(h5[toplevel_key], h5py.Group)
                            and "config_file" in h5[toplevel_key]
                            and isinstance(h5[toplevel_key]["config_file"], h5py.Group)
                            and "config" in h5[toplevel_key]["config_file"]
                            and isinstance(h5[toplevel_key]["config_file"]["config"], h5py.Group)
                        ):
                            logger.info("config_file not found: %s", toplevel_key)
                            continue

                        logger.info("config_file found: %s", toplevel_key)
                        config = h5[toplevel_key]["config_file"]["config"]
                        ini_str = "\n".join(f"{k}={config[k][0].decode('utf-8')}" for k in config.keys())
                    except (KeyError, OSError, IndexError, AttributeError, ValueError):
                        error_msg = f"Failed to read H5 config data for key {toplevel_key!r} in {h5url}"
                        logger.exception(error_msg)
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
                        logger.info("BilbyJob %s created 😊", job.id)
                        if event_id is not None:
                            job.set_event_id(event_id)
                            logger.info(" and set event_id to %s", event_id.event_id)
                        else:
                            logger.info(" and has no event_id")
                        none_succeeded = False
                    except GWDCUnknownException:
                        all_succeeded = False
                        # we don't just raise here as we want to potentially upload other jobs
                        logger.exception("Failed to create BilbyJob 😠")

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
            continue

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

        # One H5 processing attempt per invocation — if the event was successfully
        # processed (whether that means uploads succeeded, partially failed, or it was
        # intentionally ignored), we stop here so the cron job doesn't consume too
        # much time in a single pass. Failed events (where everything failed) are skipped
        # via `continue` above and will be retried on the next run.
        break


def run():
    """Entry point that ensures only one instance runs at a time via an exclusive file lock.

    If another instance already holds the lock, logs a message and returns immediately.
    Exits with code 1 if DB_PATH is not configured.
    """
    if not DB_PATH:
        logger.critical("DB_PATH is not set — this is a misconfiguration. Exiting.")
        sys.exit(1)

    lock_fd = Path(LOCK_FILE_PATH).open("w")
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
