from gwcloud_python import GWCloud
import os
import sqlite3
from datetime import datetime
import h5py
import requests
from traceback import print_exception
from tempfile import NamedTemporaryFile

print(f"==== gwosc_ingest cronjob {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ====")
try:
    from local import *
except ImportError:
    print("No local.py file found, loading settings from env")
    GWCLOUD_TOKEN = os.getenv("GWCLOUD_TOKEN")
    AUTH_ENDPOINT = os.getenv("AUTH_ENDPOINT")
    ENDPOINT = os.getenv("ENDPOINT")

EVENTNAME_SEPERATOR = "--"

GWOSC_BASE_URL = "https://gwosc.org/"

# note that you may need to manually modify the APIToken 'app' value if running locally
# since when you create a token it has the 'app' set to gwcloud but we're 
# accessing it through localhost:8000 which confuses the project detection regex
gwc = GWCloud(GWCLOUD_TOKEN, auth_endpoint=AUTH_ENDPOINT, endpoint=ENDPOINT)


# Collect list of events from GWOSC
r = requests.get(f"{GWOSC_BASE_URL}eventapi/json/allevents")
all_events = r.json()["events"]
gwosc_events = list(all_events.keys())
print(f"GWOSC events found: {len(gwosc_events)}")

# Collect list of events from GWCloud
full_gwcloud_events = [n.name for n in gwc.get_official_job_list()]
# Only those which follow the format EVENT_NAME--RUN_TYPE are considered to have a valid EVENT_NAME
gwcloud_events = list(set([n.split(EVENTNAME_SEPERATOR)[0] for n in full_gwcloud_events if len(n.split(EVENTNAME_SEPERATOR))>1]))
print(f"GWCloud events found: {len(gwcloud_events)}")

# collect list of events from sqlite db
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
cur = con.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS completed_jobs (job_id TEXT PRIMARY KEY, success BOOLEAN, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
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
event_json = r.json()
parameters = event_json["events"][event_name]['parameters']
found = [v for v in parameters.values() if v['is_preferred']]
if len(found) != 1:
    print(f"Unable to find preferred job for {event_name} 😠")
    cur.execute("INSERT INTO completed_jobs (job_id, success) VALUES (?, ?)", (event_name, False))
    con.commit()
    # print("This will continue to fail forever until a fix is implemented to skip this bad job")
    exit()
h5url = found[0]["data_url"]
local_file_path = f"/tmp/{event_name}.h5"
print("Downloading h5 file")

all_succeeded = True
with NamedTemporaryFile(mode="rb+") as f:
    with requests.get(h5url, stream=True) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
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
                    job = gwc.upload_external_job(f"{event_name}{EVENTNAME_SEPERATOR}{toplevel_key}", toplevel_key, False, ini_str, h5url)
                    print(f"BilbyJob {job.id} created 😊")
                except Exception as e:
                    all_succeeded = False
                    print("Failed to create BilbyJob 😠")
                    print_exception(e)
            else:
                print(f"config_file not found: {toplevel_key}")

cur.execute("INSERT INTO completed_jobs (job_id, success) VALUES (?, ?)", (event_name, all_succeeded))
con.commit()
print("Deleted temp h5 file")
