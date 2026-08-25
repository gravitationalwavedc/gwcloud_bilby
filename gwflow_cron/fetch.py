import hashlib
import logging
from pathlib import Path

import settings
from job_controller import FetchError

logger = logging.getLogger("gwflow_ingest.fetch")


class MD5Mismatch(Exception):
    pass


def _get(rec, key):
    if isinstance(rec, dict):
        return rec.get(key)
    return getattr(rec, key)


def _unsafe_component(value: str | None) -> bool:
    """True if a path component could traverse out of its parent directory."""
    return value is None or not isinstance(value, str) or "\x00" in value or "/" in value or value == ".."


def fetch_to_staging(jc, rec, staging_dir=None) -> Path:
    """Stage a pending-file record into the staging area and verify its md5.

    rec is a pending-file record dict-like with keys:
    id, sname, analysis_uid, path, file_name, md5_sum.

    The remote path is mapped via jc.map_remote_path (strips CIT: and rejects
    traversal/non-absolute paths), a file download is created, and the file is
    streamed into staging_dir/<sname>/<analysis_uid>/<path sans leading '/'>.
    The sname/analysis_uid components are validated to be single path segments
    and the destination is containment-checked against the staging dir so a
    crafted path cannot escape it. The md5 is verified when the record carries
    a truthy md5_sum. ClusterOffline and FetchError raised by the controller
    propagate untouched. On MD5Mismatch the staged file is removed so no bad
    file lingers.
    """
    remote = jc.map_remote_path(_get(rec, "path"))

    sname = _get(rec, "sname")
    analysis_uid = _get(rec, "analysis_uid")
    for name, value in (("sname", sname), ("analysis_uid", analysis_uid)):
        if _unsafe_component(value):
            raise FetchError(f"unsafe staging component {name!r}: {value!r}")

    file_id = jc.create_file_downloads([remote])[0]

    base = Path(staging_dir) if staging_dir else Path(settings.STAGING_DIR)
    dest = base / sname / analysis_uid / remote.lstrip("/")
    if not dest.resolve().is_relative_to(base.resolve()):
        raise FetchError(f"staged path escapes staging dir: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    jc.download(file_id, dest)

    md5_sum = _get(rec, "md5_sum")
    if md5_sum:
        digest = hashlib.md5()
        with dest.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != md5_sum:
            dest.unlink(missing_ok=True)
            raise MD5Mismatch(f"md5 mismatch for {remote}: expected {md5_sum}, got {digest.hexdigest()}")

    return dest
