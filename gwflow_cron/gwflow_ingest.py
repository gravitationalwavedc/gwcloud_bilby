import argparse
import contextlib
import copy
import fcntl
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

import manifest
import settings
import state
from fetch import fetch_to_staging
from job_controller import ClusterOffline
from portal import PortalClient

logger = logging.getLogger("gwflow_ingest")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    fh = logging.FileHandler("gwflow_ingest.log")
    fh.setLevel(logging.DEBUG)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(sh)


def _get(rec: Any, key: str):
    if isinstance(rec, dict):
        return rec.get(key)
    return getattr(rec, key)


def _with_normalized_uid(rec: Any, analysis_uid: str) -> Any:
    """Return a shallow copy of rec with analysis_uid normalized to a string."""
    rec = copy.copy(rec)
    if isinstance(rec, dict):
        rec["analysis_uid"] = analysis_uid
    else:
        rec.analysis_uid = analysis_uid
    return rec


def gwc_known_unpruned_snames(gwc_client: Any) -> set[str]:
    """Query GWCloud for active (unpruned) superevent snames."""
    jobs = gwc_client.get_gwflow_job_list(include_pruned=False)
    snames = set()
    for j in jobs:
        sname = j.get("sname") if isinstance(j, dict) else getattr(j, "sname", None)
        if sname:
            snames.add(sname)
    return snames


def phase_metadata(portal_client: Any = None, gwc_client: Any = None, con: sqlite3.Connection | None = None):
    logger.info("Starting phase_metadata")

    close_con = False
    if con is None:
        con = sqlite3.connect(settings.DB_PATH)
        con.row_factory = sqlite3.Row
        close_con = True

    try:
        cur = con.cursor()
        state.init_db(cur)

        if portal_client is None:
            portal_client = PortalClient(settings.CBCFLOW_PORTAL_URL, settings.CBCFLOW_PORTAL_TOKEN)

        start_wm = state.get_watermark(cur)
        start_last_sname = state.get_last_sname(cur)
        has_failure_in_run = False

        # Safely stream changed rows from portal
        try:
            changed_stream = portal_client.iter_changed(since=start_wm)
            for row in changed_stream:
                if not isinstance(row, dict):
                    continue
                row_ts = row.get("commit_timestamp")
                row_sname = row.get("sname")
                row_schema_ver = row.get("schema_version")
                row_commit_sha = row.get("commit_sha")

                if not row_ts or not row_sname:
                    continue

                # Tie resume check
                if start_wm and start_last_sname and (row_ts, row_sname) <= (start_wm, start_last_sname):
                    continue

                try:
                    detail = portal_client.get_superevent(row_sname)
                    files = manifest.extract_file_manifest(detail)
                    libraries = (
                        [lib["name"] for lib in detail.get("libraries", []) if isinstance(lib, dict)]
                        if isinstance(detail.get("libraries"), list)
                        else []
                    )
                    metadata = detail.get("raw_payload", {})

                    if gwc_client is not None:
                        gwc_client.upsert_gwflow_job(
                            sname=row_sname,
                            schema_version=row_schema_ver,
                            metadata=metadata,
                            libraries=libraries,
                            is_pruned=False,
                            current_history_id=row_commit_sha,
                            current_history_timestamp=row_ts,
                            files=files,
                        )

                    state.clear_failure(con, cur, row_sname)
                    if not has_failure_in_run:
                        state.set_watermark(con, cur, row_ts)
                        state.set_last_sname(con, cur, row_sname)

                except Exception as e:
                    logger.warning("Error processing %s: %s", row_sname, e)
                    state.record_failure(con, cur, row_sname, repr(e))
                    if state.get_failure_count(cur, row_sname) >= settings.MAX_RETRY_ATTEMPTS:
                        logger.exception("giving up on %s", row_sname)
                    else:
                        has_failure_in_run = True
                    continue
        except Exception as e:
            logger.exception("Failed during portal superevent sync: %s", e)

        # Prune diffing: check for snames present in GWCloud but missing upstream
        try:
            current_snames = set(portal_client.iter_current_snames())
        except Exception as e:
            logger.exception("Failed to fetch current snames from portal for prune diff: %s", e)
            current_snames = set()

        if gwc_client is not None:
            known_unpruned = gwc_known_unpruned_snames(gwc_client)
            pruned_snames = known_unpruned - current_snames

            for p_sname in pruned_snames:
                gwc_client.upsert_gwflow_job(sname=p_sname, is_pruned=True)

    finally:
        if close_con and con:
            con.close()

    logger.info("Completed phase_metadata")


def phase_bilby_children():
    logger.info("phase_bilby_children: not implemented")


def phase_file_mirror(jc: Any = None, gwc_client: Any = None, con: sqlite3.Connection | None = None):
    if jc is None or gwc_client is None:
        logger.info("phase_file_mirror: clients not wired (B1) - skipping")
        return
    logger.info("Starting phase_file_mirror")

    close_con = False
    if con is None:
        con = sqlite3.connect(settings.DB_PATH)
        con.row_factory = sqlite3.Row
        close_con = True

    try:
        cur = con.cursor()
        state.init_db(cur)

        queue = list(gwc_client.get_gwflow_pending_files())
        over_retry = set(state.failures_over(cur, settings.MAX_RETRY_ATTEMPTS))
        bytes_done = files_done = 0
        for rec in queue:
            if not settings.BACKFILL and (
                files_done >= settings.MAX_FILES_PER_RUN or bytes_done >= settings.MAX_BYTES_PER_RUN
            ):
                break
            analysis_uid = _get(rec, "analysis_uid") or ""
            key = f"{_get(rec, 'sname')}/{analysis_uid}/{_get(rec, 'path')}"
            if key in over_retry:
                continue
            staged = None
            try:
                fetch_rec = _with_normalized_uid(rec, analysis_uid)
                staged = fetch_to_staging(jc, fetch_rec)
                size = staged.stat().st_size
                gwc_client.upload_gwflow_file(_get(rec, "id"), staged)
                bytes_done += size
                files_done += 1
                state.clear_failure(con, cur, key)
            except ClusterOffline:
                logger.warning("cluster offline - deferring remaining files")
                break
            except Exception as e:
                state.record_failure(con, cur, key, repr(e))
            finally:
                if staged is not None:
                    staged.unlink(missing_ok=True)
    finally:
        if close_con and con:
            con.close()

    logger.info("Completed phase_file_mirror")


def parse_args(args=None):
    parser = argparse.ArgumentParser(description="GWFlow ingest cron job")
    parser.add_argument("--backfill", action="store_true", help="Lift per-run caps for backfill mode")
    return parser.parse_args(args)


def run(args=None):
    parsed = parse_args(args)
    settings.BACKFILL = parsed.backfill

    settings.validate_settings()

    lock_path = Path(settings.DB_PATH).with_suffix(".lock")
    lock_file = None
    try:
        lock_file = lock_path.open("w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        logger.warning("Another instance of gwflow_ingest is already running.")
        if lock_file:
            lock_file.close()
        return 0

    try:
        logger.info("Starting gwflow_ingest run")
        con = sqlite3.connect(settings.DB_PATH)
        con.row_factory = sqlite3.Row
        state.init_db(con)

        phase_metadata(con=con)
        phase_bilby_children()
        phase_file_mirror()

        con.close()
        logger.info("Completed gwflow_ingest run")
        return 0
    finally:
        if lock_file:
            with contextlib.suppress(OSError):
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


if __name__ == "__main__":
    sys.exit(run())
