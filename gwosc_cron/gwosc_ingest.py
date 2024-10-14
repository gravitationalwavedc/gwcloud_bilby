from gwcloud_python import GWCloud
import h5py
import requests

gwc = GWCloud(gwcloud_token)

GWOSC_BASE_URL = "https://gwosc.org/"

# Collect list of events from GWOSC
r = requests.get(f"{GWOSC_BASE_URL}eventapi/json/allevents")
all_events = r.json()["events"]
gwosc_events = list(all_events.keys())
print(f"GWOSC events found: {len(gwosc_events)}")

# Collect list of events from GWCloud
# TODO: Filter this to only get those jobs which were made by this tool (the system user)
gwcloud_events = [j.name for j in gwc.get_official_job_list()]
print(f"GWCloud events found: {len(gwcloud_events)}")

# Find non-matching dataset names
not_found = [j for j in gwosc_events if j not in gwcloud_events]
print(f"Not matching events: {len(not_found)}")

for event_name in not_found[0:1]:
    print(all_events[event_name]["jsonurl"])
    r = requests.get(all_events[event_name]["jsonurl"])
    event_json = r.json()
    parameters = event_json["events"][event_name]['parameters']
    found = [v for v in parameters.values() if v['is_preferred']][0]
    if not found:
        print(f"Unable to find preferred job for {event_name}")
        break
    h5url = found["data_url"]
    local_file_path = f"/tmp/{event_name}.h5"
    print("Saving h5 file")
    # with requests.get(h5url, stream=True) as r:
    #     r.raise_for_status()
    #     with open(local_file_path, 'wb') as f:
    #         for chunk in r.iter_content(chunk_size=8192):
    #             f.write(chunk)
    print("Saved")

    
    # Load the h5 file, and read in the bilby ini file(s)
    h5 = h5py.File(local_file_path)
    for k in h5.keys():
        if h5[k]["config_file"]["config"]:
           print('yes') 
