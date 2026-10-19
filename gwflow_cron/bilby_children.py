import configparser
import logging
import math
import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("gwflow_ingest.bilby_children")


class StageError(Exception):
    """Raised when a supporting file cannot be safely staged into the job tree."""


_TRUTHY_PREFERRED = (True, "true", "True", "yes")
_HDF5_SUFFIXES = {".hdf5", ".h5"}


SUPPORTED_BILBY_SOFTWARE = {"bilby", "BILBY", "bilby_pipe"}
_SUPPORTED_STATUSES = {"complete", "running", "stuck", "unstarted", "cancelled"}


@dataclass(frozen=True)
class Rejection:
    sname: str | None
    analysis_uid: str | None
    role: str | None
    available_file_systems: tuple[str, ...]
    reason: str
    index: int | None = None

    @property
    def fail_key(self) -> str:
        identity = self.analysis_uid
        if not identity:
            identity = f"analyses[{self.index}]" if self.index is not None else "detail"
        return f"bilby:{self.sname}/{identity}" if self.sname else f"bilby:{identity}"


def validate_supported_software():
    """Fail closed unless the checked-in software allowlist is usable."""
    valid = (
        isinstance(SUPPORTED_BILBY_SOFTWARE, set)
        and bool(SUPPORTED_BILBY_SOFTWARE)
        and all(isinstance(name, str) and bool(name) for name in SUPPORTED_BILBY_SOFTWARE)
    )
    if not valid:
        logger.critical("SUPPORTED_BILBY_SOFTWARE must be a non-empty set of non-empty strings")
        raise SystemExit(1)


def _rejection(sname, uid, reason, *, role=None, file_systems=(), index=None):
    return Rejection(
        sname=sname,
        analysis_uid=uid if isinstance(uid, str) and uid else None,
        role=role,
        available_file_systems=tuple(file_systems),
        reason=reason,
        index=index,
    )


def _check_pe_fields(sname, analysis, index):
    uid = analysis.get("uid")
    if not isinstance(uid, str) or not uid:
        return _rejection(sname, uid, "uid missing or not a non-empty string", index=index)

    status = analysis.get("status")
    if status not in _SUPPORTED_STATUSES:
        return _rejection(sname, uid, "status missing or unsupported", index=index)

    if not isinstance(analysis.get("deprecated"), bool):
        return _rejection(sname, uid, "deprecated missing or not a boolean", index=index)

    if "software" not in analysis:
        return _rejection(sname, uid, "software missing", index=index)
    if analysis["software"] is not None and not isinstance(analysis["software"], dict):
        return _rejection(sname, uid, "software malformed", index=index)

    for field in ("input_files", "output_files", "configurations"):
        if not isinstance(analysis.get(field), list):
            return _rejection(sname, uid, f"{field} missing or not an array", index=index)

    return None


def _relationships_with_role(sname, uid, relationships, role, index):
    matches = []
    for relationship in relationships:
        if (
            not isinstance(relationship, dict)
            or not isinstance(relationship.get("role"), str)
            or not isinstance(relationship.get("file"), dict)
        ):
            return None, _rejection(
                sname,
                uid,
                "file relationship malformed",
                role=role,
                index=index,
            )
        if relationship["role"] == role:
            matches.append(relationship)
    return matches, None


def _select_location(sname, uid, role, file_data, file_systems, index):
    locations = file_data.get("locations")
    if not isinstance(locations, list):
        return None, _rejection(
            sname,
            uid,
            "file locations missing or not an array",
            role=role,
            index=index,
        )

    available = set()
    ranked = []
    ranks = {file_system: rank for rank, file_system in enumerate(file_systems)}
    for location in locations:
        if not isinstance(location, dict):
            return None, _rejection(sname, uid, "file location malformed", role=role, index=index)
        file_system = location.get("file_system")
        path = location.get("path")
        url = location.get("url")
        if (
            not isinstance(file_system, str)
            or not isinstance(path, str)
            or (url is not None and not isinstance(url, str))
        ):
            return None, _rejection(sname, uid, "file location malformed", role=role, index=index)
        available.add(file_system)
        if file_system in ranks and path.strip():
            ranked.append((ranks[file_system], path, (0, "") if url is None else (1, url), path))

    if not ranked:
        return None, _rejection(
            sname,
            uid,
            "no accessible location",
            role=role,
            file_systems=sorted(available),
            index=index,
        )
    return min(ranked)[3], None


def _select_file(sname, uid, role, relationship, file_systems, index):
    file_data = relationship["file"]
    path, rejection = _select_location(sname, uid, role, file_data, file_systems, index)
    if rejection:
        return None, rejection

    if "md5sum" not in file_data or (file_data["md5sum"] is not None and not isinstance(file_data["md5sum"], str)):
        return None, _rejection(
            sname,
            uid,
            "file md5sum missing or malformed",
            role=role,
            index=index,
        )

    return {"path": path, "md5_sum": file_data["md5sum"]}, None


def _select_analysis(sname, analysis, file_systems, index):
    """Select one eligible Bilby PE analysis and report any rejection."""
    uid = analysis.get("uid") if isinstance(analysis, dict) else None
    if (
        not isinstance(analysis, dict)
        or not isinstance(analysis.get("type"), str)
        or analysis["type"] not in {"pe", "event_validation"}
    ):
        return None, [_rejection(sname, uid, "malformed analysis type", index=index)]

    if analysis["type"] == "event_validation":
        return None, []

    rejection = _check_pe_fields(sname, analysis, index)
    if rejection:
        return None, [rejection]

    uid = analysis["uid"]
    software = analysis["software"]
    if software is None:
        return None, []
    if not isinstance(software.get("name"), str):
        return None, [
            _rejection(
                sname,
                uid,
                "software.name missing or not a string",
                index=index,
            )
        ]
    software_name = software["name"]
    if software_name not in SUPPORTED_BILBY_SOFTWARE:
        return None, []

    malformed_configuration = any(not isinstance(configuration, dict) for configuration in analysis["configurations"])
    if malformed_configuration:
        return None, [_rejection(sname, uid, "configuration malformed", index=index)]

    configurations = [
        configuration
        for configuration in analysis["configurations"]
        if configuration.get("type") == "pe" and configuration.get("uid") == f"{uid}:configuration"
    ]
    if not configurations:
        return None, []
    if len(configurations) > 1:
        return None, [_rejection(sname, uid, "multiple pe configurations", index=index)]

    config_relationships, rejection = _relationships_with_role(sname, uid, analysis["input_files"], "config", index)
    if rejection:
        return None, [rejection]
    if not config_relationships:
        return None, []
    if len(config_relationships) > 1:
        return None, [
            _rejection(
                sname,
                uid,
                "multiple config relationships",
                role="config",
                index=index,
            )
        ]

    config_file, rejection = _select_file(
        sname,
        uid,
        "config",
        config_relationships[0],
        file_systems,
        index,
    )
    if rejection:
        return None, [rejection]

    optional_files = {}
    for role, output_name in (
        ("result", "result_file"),
        ("pesummary", "pesummary_result_file"),
    ):
        relationships, rejection = _relationships_with_role(sname, uid, analysis["output_files"], role, index)
        if rejection:
            return None, [rejection]
        if len(relationships) > 1:
            return None, [
                _rejection(
                    sname,
                    uid,
                    f"multiple {role} relationships",
                    role=role,
                    index=index,
                )
            ]
        if not relationships:
            optional_files[output_name] = None
            continue

        file_ref, rejection = _select_file(sname, uid, role, relationships[0], file_systems, index)
        if rejection and rejection.reason == "no accessible location":
            logger.warning(
                "optional file unavailable: sname=%s analysis_uid=%s role=%s available_file_systems=%s reason=%s",
                rejection.sname,
                rejection.analysis_uid,
                rejection.role,
                rejection.available_file_systems,
                rejection.reason,
            )
            optional_files[output_name] = None
            continue
        if rejection:
            return None, [rejection]
        optional_files[output_name] = file_ref

    return {
        "uid": uid,
        "config_file": config_file,
        "result_file": optional_files["result_file"],
        "pesummary_result_file": optional_files["pesummary_result_file"],
        "software": software_name,
    }, []


def select_bilby_analyses(sname, detail, file_systems):
    """Select canonical Bilby PE analyses and report malformed candidates."""
    if not isinstance(detail, dict) or not isinstance(detail.get("analyses"), list):
        return [], [_rejection(sname, None, "detail analyses must be an array")]

    selected = []
    rejections = []
    for index, analysis in enumerate(detail["analyses"]):
        selection, analysis_rejections = _select_analysis(sname, analysis, file_systems, index)
        if selection is not None:
            selected.append(selection)
        rejections.extend(analysis_rejections)

    counts = {}
    for item in selected:
        counts[item["uid"]] = counts.get(item["uid"], 0) + 1
    duplicates = sorted(uid for uid, count in counts.items() if count > 1)
    if duplicates:
        for uid in duplicates:
            rejections.append(_rejection(sname, uid, "duplicate eligible uid"))
        return [], rejections

    return selected, rejections


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


def _ini_outdir(ini_text: str) -> str | None:
    """Return the absolute `outdir` value from the ini, or None.

    Parses with interpolation disabled so `%` characters in values are not
    treated as configparser interpolation markers.
    """
    if not ini_text:
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(ini_text)
    except configparser.Error:
        return None
    for section in parser.sections():
        try:
            value = parser.get(section, "outdir")
        except (configparser.NoOptionError, configparser.NoSectionError):
            continue
        if value and value.startswith("/"):
            return value
    return None


def resolve_missing_path(p: str, ini_text: str, result_file: str | None) -> str | None:
    """Return an absolute CIT path for a raw ini file path `p`, or None when unresolvable.

    Absolute paths are returned as-is. Relative paths are resolved against the
    ini's `outdir` value (absolute CIT path), falling back to the directory of
    `result_file`. Returns None when no absolute path can be derived.
    """
    if p.startswith("/"):
        return p

    outdir = _ini_outdir(ini_text)
    if outdir:
        return outdir.rstrip("/") + "/" + p

    if result_file:
        return str(Path(result_file).parent) + "/" + p

    return None


def _tree_relative_target(p: str) -> str:
    """Return the tree-relative target for a missing path, or raise StageError.

    Validates the raw missing path before any fetch or copy: rejects empty
    paths, NUL bytes, `..` traversal, and collisions with the tree's
    reserved top-level entries (`data`, `result`, `results_page`) or a
    `*_config_complete.ini` filename. Callers use this to validate a
    destination *before* mutating the tree.
    """
    rel = p.lstrip("/")
    if not rel:
        raise StageError(f"empty relative path for {p!r}")
    if "\x00" in rel:
        raise StageError(f"NUL byte in path {p!r}")
    parts = Path(rel).parts
    if not parts:
        raise StageError(f"empty relative path for {p!r}")
    if ".." in parts:
        raise StageError(f"path traversal in {p!r}")

    first = parts[0]
    if first in ("data", "result", "results_page"):
        raise StageError(f"collision with reserved tree entry {first!r} for {p!r}")
    if Path(rel).name.endswith("_config_complete.ini"):
        raise StageError(f"collision with config_complete.ini for {p!r}")
    return rel


def stage_supporting_files(tree: Path, missing: list[str], staged_files: dict[str, Path]) -> None:
    """Copy each staged supporting file into the job tree at `p.lstrip("/")`.

    `missing` is expected to be deduped by the caller. Raises StageError on
    unsafe paths (`..` segments, NUL bytes, empty) or on collision with the
    tree's reserved top-level entries (`data`, `result`, `results_page`) or a
    `*_config_complete.ini` filename. Never clobbers existing tree content.
    """
    tree = Path(tree)
    tree_root = tree.resolve()

    for p in missing:
        rel = _tree_relative_target(p)

        src = staged_files.get(p)
        if src is None:
            continue

        dest = tree / rel
        if not dest.resolve().is_relative_to(tree_root):
            raise StageError(f"destination escapes tree root for {p!r}")
        # fetch_to_staging already staged absolute supporting files at their final
        # tree path (STAGING_DIR/<sname>/<uid>/<path>), so src and dest may be
        # the same file. Skip the copy in that case rather than raising
        # SameFileError.
        if Path(src).resolve() != dest.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


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
            if isinstance(ev, dict) and (ev.get("uid") == preferred_uid or ev.get("UID") == preferred_uid):
                chosen = ev
                break
    if chosen is None:
        for ev in events:
            if isinstance(ev, dict):
                state_val = ev.get("state") or ev.get("State")
                if isinstance(state_val, str) and state_val.lower() == "preferred":
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

    event_uid = chosen.get("uid") or chosen.get("UID")
    if not isinstance(event_uid, str) or not event_uid:
        return None

    gps_time = chosen.get("gps_time")
    if gps_time is None:
        gps_time = chosen.get("gpstime")
    if gps_time is None:
        gps_time = chosen.get("GPSTime")
    if gps_time is None:
        gps_time = gracedb.get("preferred_event_gps")
    if gps_time is None:
        gps_time = gracedb.get("gps_time")

    try:
        parsed = float(gps_time)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return event_uid, parsed
