from gwcloud_python import GWCloud
import h5py
import requests

EVENTNAME_SEPERATOR = "--"

# this is the localhost:8000 token
# note that you may need to manually modify the APIToken 'app' value 
# since when you create a token it has the 'app' set to gwcloud but we're 
# accessing it through localhost:8000 which confuses the project detection regex
gwc = GWCloud(gwcloud_token, auth_endpoint="http://localhost:8000/graphql", endpoint="http://localhost:8001/graphql")

GWOSC_BASE_URL = "https://gwosc.org/"

# Collect list of events from GWOSC
r = requests.get(f"{GWOSC_BASE_URL}eventapi/json/allevents")
all_events = r.json()["events"]
gwosc_events = list(all_events.keys())
print(f"GWOSC events found: {len(gwosc_events)}")

# Collect list of events from GWCloud
# TODO: Filter this to only get those jobs which were made by this tool (the system user)
# TODO: Modify this list to only include the event ID, rather than eventID__variant
gwcloud_events = [j.name for j in gwc.get_official_job_list()]
print(f"GWCloud events found: {len(gwcloud_events)}")

# Find non-matching dataset names
not_found = [j for j in gwosc_events if j not in gwcloud_events]
print(f"Not matching events: {len(not_found)}")

if len(not_found) == 0:
    print("Nothing to do 😊")
    exit()

event_name = not_found[0]
print(all_events[event_name]["jsonurl"])
r = requests.get(all_events[event_name]["jsonurl"])
event_json = r.json()
parameters = event_json["events"][event_name]['parameters']
found = [v for v in parameters.values() if v['is_preferred']][0]
if not found:
    print(f"Unable to find preferred job for {event_name} 😠")
    print("This will continue to fail forever until a fix is implemented to skip this bad job")
    exit()
h5url = found["data_url"]
local_file_path = f"/tmp/{event_name}.h5"
print("Saving h5 file")
with requests.get(h5url, stream=True) as r:
    r.raise_for_status()
    with open(local_file_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
print("Saved")

# local_file_path = "/home/owen/code/adacs/gwcloud/gwcloud_bilby/gwosc_cron/GW230529_181500-v1.h5"

# Load the h5 file, and read in the bilby ini file(s)
with h5py.File(local_file_path) as h5:
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
                print("Failed to create BilbyJob 😠")
                print(e)
                pass
        else:
            print(f"config_file not found: {toplevel_key}")



# delete h5 file
# although do we need to do this if we're rerunning the image each time
