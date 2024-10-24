from gwcloud_python import GWCloud
import os
import re
import sqlite3
from datetime import datetime
import h5py
import requests
from traceback import print_exception
from tempfile import NamedTemporaryFile

try:
    from local import *
except ImportError:
    print("No local.py file found, loading settings from env")
    GWCLOUD_TOKEN = os.getenv("GWCLOUD_TOKEN")
    AUTH_ENDPOINT = os.getenv("AUTH_ENDPOINT")
    ENDPOINT = os.getenv("ENDPOINT")

EVENTNAME_SEPERATOR = "--"

def fix_job_name(name):
    return re.sub("[^a-z0-9_-]", "-", name, flags=re.IGNORECASE)

def build_bilbyjob_name(event_name, config_name):
    return fix_job_name(f"{event_name}{EVENTNAME_SEPERATOR}{config_name}")

def check_and_download():
    print(f"==== gwosc_ingest cronjob {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ====")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS completed_jobs (job_id TEXT PRIMARY KEY, success BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    def save_sqlite_job(job_id, success):
        cur.execute("INSERT INTO completed_jobs (job_id, success) VALUES (?, ?)", (job_id, success))
        con.commit()

# note that you may need to manually modify the APIToken 'app' value if running locally
# since when you create a token it has the 'app' set to gwcloud but we're 
# accessing it through localhost:8000 which confuses the project detection regex
    gwc = GWCloud(GWCLOUD_TOKEN, auth_endpoint=AUTH_ENDPOINT, endpoint=ENDPOINT)


# Collect list of events from GWOSC
    r = requests.get("https://gwosc.org/eventapi/json/allevents")
    if r.status_code != 200:
        print(f"Unable to fetch allevents json (status: {r.status_code})")
        exit()
    all_events = r.json()["events"]
    gwosc_events = [ fix_job_name(k) for k in all_events.keys()]
    print(f"GWOSC events found: {len(gwosc_events)}")

# Collect list of events from GWCloud
    full_gwcloud_events = [n.name for n in gwc.get_official_job_list()]
# Only those which follow the format EVENT_NAME--RUN_TYPE are considered to have a valid EVENT_NAME
    gwcloud_events = list(set([fix_job_name(n.split(EVENTNAME_SEPERATOR)[0]) for n in full_gwcloud_events if len(n.split(EVENTNAME_SEPERATOR))>1]))
    print(f"GWCloud events found: {len(gwcloud_events)}")

# fetch event_ids from gwcloud and turn them into a dict
    full_gwcloud_event_ids = gwc.get_all_event_ids()
    gwcloud_event_ids = {z.event_id:z for z in full_gwcloud_event_ids}

# collect list of events from sqlite db
    sqlite_rows = cur.execute("SELECT * FROM completed_jobs")
    sqlite_events = [j["job_id"] for j in sqlite_rows.fetchall()]

    print(f"sqlite events found: {len(sqlite_events)}")
    print(f"Potential bad runs found: {len(sqlite_events) - len(gwcloud_events)}")

# Find non-matching dataset names
    not_found = [j for j in gwosc_events if j not in sqlite_events]
    print(f"Not matching events: {len(not_found)}")

    if len(not_found) == 0:
        print("Nothing to do 😊")
        exit()

    event_name = not_found[0]
    print(f"{event_name}: {all_events[event_name]["jsonurl"]}")
    r = requests.get(all_events[event_name]["jsonurl"])
    if r.status_code != 200:
        print(f"Unable to fetch event json (status: {r.status_code}, event: {event_name}, url: {all_events[event_name]["jsonurl"]})")
        exit()
    event_json = r.json()
    parameters = event_json["events"][event_name]['parameters']
    common_name = event_json["events"][event_name]['commonName']
    gps = event_json["events"][event_name]["GPS"]
    gracedb_id = event_json["events"][event_name]["gracedb_id"]
    found = [v for v in parameters.values() if v['is_preferred']]
    if len(found) != 1:
        print(f"Unable to find preferred job for {event_name} 😠")
        save_sqlite_job(event_name, False)
        # print("This will continue to fail forever until a fix is implemented to skip this bad job")
        exit()
    h5url = found[0].get("data_url")
    if h5url == "" or h5url is None:
        print(f"Preferred job for {event_name} does not contain a dataurl 😠")
        save_sqlite_job(event_name, False)
        exit()

# See if there is already an event_id for this event
    event_id = None
    if re.match(r'^GW\d{6}_\d{6}$', common_name):
        event_id = gwcloud_event_ids.get(common_name, None)
        if event_id is None:
            # we need to create one
            event_id = gwc.create_event_id(common_name, gps, gracedb_id)
            print(f"Created a new event_id: {common_name}")
        else:
            print(f"event_id already found: {common_name}")
    else:
        print(f"{common_name} is not a valid event_id, uploading job without one")

    print("Downloading h5 file")
    all_succeeded = True
    none_succeeded = True
    with NamedTemporaryFile(mode="rb+") as f:
        try:
            with requests.get(h5url, stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception:
            print(f"Downloading {h5url} failed 😠")
            raise

        print("Download complete")

        # Load the h5 file, and read in the bilby ini file(s)
        with h5py.File(f) as h5:
            print(f"Found keys: {list(h5.keys())}")
            for toplevel_key in h5.keys():
                if 'config_file' in h5[toplevel_key] and 'config' in h5[toplevel_key]['config_file']:
                    print(f"config_file found: {toplevel_key}")
                    config = h5[toplevel_key]['config_file']['config']
                    ini_lines = []
                    for k in config.keys():
                        ini_lines.append(f"{k}={config[k][0].decode('utf-8')}")
                    ini_str = "\n".join(ini_lines)
                    try:
                        job = gwc.upload_external_job(build_bilbyjob_name(event_name, toplevel_key), toplevel_key, False, ini_str, h5url)
                        print(f"BilbyJob {job.id} created 😊")
                        if event_id is not None:
                            job.set_event_id(event_id)
                            print(f" and set event_id to {event_id.event_id}")
                        else:
                            print(" and has no event_id")
                        none_succeeded = False
                    except Exception as e:
                        all_succeeded = False
                        print("Failed to create BilbyJob 😠")
                        # we don't just raise here as we want to potentially upload other jobs
                        print_exception(e)
                else:
                    print(f"config_file not found: {toplevel_key}")

    save_sqlite_job(event_name, all_succeeded and not none_succeeded)
    print("Deleted temp h5 file")


if __name__ == "__main__":
    check_and_download()
