import logging
import re
import shutil
import tarfile
from pathlib import Path

logger = logging.getLogger("gwflow_ingest.bilby_children")


_TRUTHY_PREFERRED = (True, "true", "True", "yes")
_HDF5_SUFFIXES = {".hdf5", ".h5"}


def find_bilby_pe_analyses(detail: dict) -> list[dict]:
    """Walk detail["pe"]["results"] and return bilby-PE analyses with config_file.

    A result is kept when:
      - re.search(r"bilby", inference_software, re.IGNORECASE) matches, AND
      - config_file is a dict with a truthy path, AND
      - uid is a non-empty string.

    Returns [{uid, config_file, result_file, pesummary_result_file, software}].
    Unknown / malformed shapes are skipped, never raised.
    """
    if not isinstance(detail, dict):
        return []

    pe_section = detail.get("pe")
    if not isinstance(pe_section, dict):
        return []

    results = pe_section.get("results")
    if not isinstance(results, list):
        return []

    analyses: list[dict] = []
    for res in results:
        if not isinstance(res, dict):
            continue

        uid = res.get("uid", "")
        if not isinstance(uid, str) or not uid:
            continue

        inference_software = res.get("inference_software", "")
        if not re.search(r"bilby", str(inference_software), re.IGNORECASE):
            continue

        config_file = res.get("config_file")
        if not isinstance(config_file, dict) or not config_file.get("path"):
            continue

        analyses.append(
            {
                "uid": uid,
                "config_file": config_file,
                "result_file": res.get("result_file"),
                "pesummary_result_file": res.get("pesummary_result_file"),
                "software": inference_software,
            }
        )

    return analyses


def _set_ini_label(ini_text: str, name: str) -> str:
    """Override the ini label to name. Replaces the first existing label line (case-insensitive,
    whitespace tolerant); otherwise prepends "label = {name}\\n".
    """
    pattern = re.compile(r"^label\s*=[^\n]*", re.MULTILINE | re.IGNORECASE)
    replacement = f"label = {name}"
    if pattern.search(ini_text):
        return pattern.sub(replacement, ini_text, count=1)
    return f"{replacement}\n{ini_text}"


def synthesize_job_tree(workdir: Path, name: str, ini_text: str, result_files: list[Path]) -> Path:
    """Build the standard uploaded-job layout gwcloud's upload handler expects.

    Layout:
        workdir/data/                 (empty ok)
        workdir/result/               (primary result file at index 0 renamed to
                                       result.hdf5 when hdf5/h5; otherwise keeps basename.
                                       Subsequent files keep their basenames.)
        workdir/results_page/         (empty ok)
        workdir/{name}_config_complete.ini
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    for sub in ("data", "result", "results_page"):
        (workdir / sub).mkdir(parents=True, exist_ok=True)

    result_dir = workdir / "result"
    for idx, src in enumerate(result_files):
        src_path = Path(src)
        if idx == 0 and src_path.suffix.lower() in _HDF5_SUFFIXES:
            dest = result_dir / "result.hdf5"
        else:
            dest = result_dir / src_path.name
        shutil.copy2(src_path, dest)

    ini_path = workdir / f"{name}_config_complete.ini"
    ini_path.write_text(_set_ini_label(ini_text, name), encoding="utf-8")

    return workdir


def make_archive(tree: Path, dest: Path) -> Path:
    """tar.gz the tree contents with a '.' root member (standard `tar -czf .` layout).

    gwcloud's upload handler unpacks with `tar -xvf <file> .`, which requires the
    archive to contain a '.' member; arcnames relative to the tree root alone are
    rejected as "Invalid or corrupt tar.gz file".
    """
    tree = Path(tree)
    dest = Path(dest)
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(tree, arcname=".")
    return dest


def resolve_event_id_for(sname: str, detail: dict) -> tuple[str, float] | None:
    """Return (event_uid, gps_time) from the payload's GraceDB preferred event.

    Defensive parsing: returns None on any missing / malformed section.
    sname is unused in resolution (reserved for future extension / logging symmetry).
    """
    del sname  # unused; signature kept symmetric with the design spec

    if not isinstance(detail, dict):
        return None

    gracedb = detail.get("gracedb")
    if not isinstance(gracedb, dict):
        gracedb = detail.get("GraceDB")
    if not isinstance(gracedb, dict):
        return None

    events = gracedb.get("events")
    if not events:
        events = gracedb.get("Events")
    if not isinstance(events, list) or not events:
        return None

    preferred_uid = gracedb.get("preferred_event")
    if not preferred_uid:
        preferred_uid = gracedb.get("preferred_event_uid")

    chosen = None
    if preferred_uid:
        for ev in events:
            if isinstance(ev, dict) and ev.get("uid") == preferred_uid:
                chosen = ev
                break
    if chosen is None:
        for ev in events:
            if isinstance(ev, dict) and ev.get("is_preferred") in _TRUTHY_PREFERRED:
                chosen = ev
                break
    if chosen is None:
        for ev in events:
            if isinstance(ev, dict) and ev.get("preferred") in _TRUTHY_PREFERRED:
                chosen = ev
                break
    if chosen is None:
        chosen = events[0]

    if not isinstance(chosen, dict):
        return None

    event_uid = chosen.get("uid")
    if not isinstance(event_uid, str) or not event_uid:
        return None

    gps_time = chosen.get("gps_time")
    if gps_time is None:
        gps_time = chosen.get("gpstime")
    if gps_time is None:
        gps_time = gracedb.get("preferred_event_gps")
    if gps_time is None:
        gps_time = gracedb.get("gps_time")

    try:
        return event_uid, float(gps_time)
    except (TypeError, ValueError):
        return None
