from gwcloud_python import GWCloud
import os
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
    AUTH_ENDPOINT = os.getenv("AUTH_ENDPOINT")
    ENDPOINT = os.getenv("ENDPOINT")
    DB_PATH = os.getenv("DB_PATH")

EVENTNAME_SEPERATOR = "--"


def fix_job_name(name):
    return re.sub("[^a-z0-9_-]", "-", name, flags=re.IGNORECASE)


def build_bilbyjob_name(event_name, config_name):
    return fix_job_name(f"{event_name}{EVENTNAME_SEPERATOR}{config_name}")


def check_and_download():
    logger.info(
        f"==== gwosc_ingest cronjob {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===="
    )
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS completed_jobs (job_id TEXT PRIMARY KEY, success BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reason TEXT, reason_data TEXT, catalog_shortname TEXT,common_name, all_succeeded INT, none_succeeded INT, is_latest_version BOOLEAN)"  # noqa
    )

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

    # note that you may need to manually modify the APIToken 'app' value if running locally
    # since when you create a token it has the 'app' set to gwcloud but we're
    # accessing it through localhost:8000 which confuses the project detection regex
    gwc = GWCloud(GWCLOUD_TOKEN, auth_endpoint=AUTH_ENDPOINT, endpoint=ENDPOINT)

    # Collect list of events from GWOSC
    r = requests.get("https://gwosc.org/eventapi/json/allevents")
    if r.status_code != 200:
        logger.critical(f"Unable to fetch allevents json (status: {r.status_code})")
        exit()

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
        exit()

    event_name = jobs_delta[0]

    logger.info(f"{event_name}: {all_events[event_name]['jsonurl']}")

    r = requests.get(all_events[event_name]["jsonurl"])
    if r.status_code != 200:
        logger.critical(
            f"Unable to fetch event json (status: {r.status_code}, event: "
            f"{event_name}, url: {all_events[event_name]['jsonurl']})"
        )
        # We assume this is a transient issue and don't mark the job as failed
        exit()

    event_json = r.json()
    event_json = event_json["events"][event_name]
    parameters = event_json["parameters"]
    common_name = event_json["commonName"]
    catalog_shortname = event_json["catalog.shortName"]

    shared_common_names = [
        k for k, v in all_events.items() if v["commonName"] == common_name
    ]
    is_latest_version = True
    if len(shared_common_names) > 1:
        versions_available = [
            int(re.search(r"-v(\d+)$", cn).groups()[0]) for cn in shared_common_names
        ]
        current_version = int(re.search(r"-v(\d+)$", event_name).groups()[0])
        is_latest_version = current_version == max(versions_available)

    gps = event_json["GPS"]
    gracedb_id = event_json["gracedb_id"]

    # Check if this should be skipped for being in the wrong type of catalog
    ignore_patterns = [
        "marginal",
        "preliminary",
        "initial_ligo_virgo",
    ]
    for pattern in ignore_patterns:
        if re.search(pattern, catalog_shortname, flags=re.IGNORECASE):
            logger.info(
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
            exit()

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
        exit()

    h5url = found[0].get("data_url")
    if not h5url:
        logger.error(f"Preferred job for {event_name} does not contain a dataurl 😠")
        save_sqlite_job(
            event_name, common_name, catalog_shortname, False, "no dataurl", -1
        )
        exit()

    # See if there is already an event_id for this event
    event_id = None
    if re.match(r"^GW\d{6}_\d{6}$", common_name):
        event_id = gwcloud_event_ids.get(common_name, None)
        if event_id is None:
            # we need to create one
            event_id = gwc.create_event_id(common_name, gps, gracedb_id)
            logger.info(f"Created a new event_id: {common_name}")
        else:
            logger.info(f"event_id already found: {common_name}")
    else:
        logger.info(f"{common_name} is not a valid event_id, uploading job without one")

    logger.info("Downloading h5 file")
    logger.info(h5url)
    all_succeeded = True
    none_succeeded = True
    with NamedTemporaryFile(mode="rb+") as f:
        try:
            with requests.get(h5url, stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception:
            # we assume that this is a transient issue and don't mark the job as failed
            logger.critical(f"Downloading {h5url} failed 😠", exc_info=True)
            exit()

        logger.info("Download complete")

        # Load the h5 file, and read in the bilby ini file(s)
        with h5py.File(f) as h5:
            logger.info(f"Found keys: {list(h5.keys())}")
            for toplevel_key in h5.keys():
                if (
                    isinstance(h5[toplevel_key], h5py.Group)
                    and "config_file" in h5[toplevel_key]
                    and isinstance(h5[toplevel_key]["config_file"], h5py.Group)
                    and "config" in h5[toplevel_key]["config_file"]
                    and isinstance(
                        h5[toplevel_key]["config_file"]["config"], h5py.Group
                    )
                ):
                    logger.info(f"config_file found: {toplevel_key}")
                    config = h5[toplevel_key]["config_file"]["config"]
                    ini_lines = []
                    for k in config.keys():
                        ini_lines.append(f"{k}={config[k][0].decode('utf-8')}")
                    ini_str = "\n".join(ini_lines)
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
                else:
                    logger.info(f"config_file not found: {toplevel_key}")

    # If we've iterated all the potential BilbyJobs, save the info to the sqlite database
    #
    # The job is considered successful if _all_ of the bilby configs found were able
    # to be successfully submitted, _and_ there was at least one job submitted.
    #
    # If no jobs were submitted, it is considered "unsuccessful" even though its most
    # likely a problem with data missing from the h5 file or event json
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


if __name__ == "__main__":
    check_and_download()
