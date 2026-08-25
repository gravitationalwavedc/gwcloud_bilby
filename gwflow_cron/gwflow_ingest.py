import argparse
import contextlib
import copy
import fcntl
import logging
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from gwcloud_python import GWCloud

import manifest
import settings
import state
from bilby_children import find_bilby_pe_analyses, make_archive, resolve_event_id_for, synthesize_job_tree
from fetch import _get, fetch_to_staging
from job_controller import ClusterOffline, JobControllerClient
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


def _with_normalized_uid(rec: Any, analysis_uid: str) -> Any:
    """Return a shallow copy of rec with analysis_uid normalized to a string."""
    rec = copy.copy(rec)
    if isinstance(rec, dict):
        rec["analysis_uid"] = analysis_uid
    else:
        rec.analysis_uid = analysis_uid
    return rec


def rec_for(file_ref: dict, sname: str, uid: str) -> dict:
    """Build a pending-file-shaped record for fetch_to_staging."""
    return {
        "sname": sname,
        "analysis_uid": uid,
        "path": file_ref["path"],
        "file_name": Path(file_ref["path"]).name,
        "md5_sum": file_ref.get("md5_sum") or "",
    }


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
        state.clear_changed_snames(con, cur)

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
                    if not isinstance(detail, dict):
                        logger.warning("Skipping %s: non-dict superevent detail", row_sname)
                        continue
                    files = manifest.extract_file_manifest(detail)
                    libraries = (
                        [lib["name"] for lib in detail.get("libraries", []) if isinstance(lib, dict) and "name" in lib]
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
                    state.record_changed_sname(con, cur, row_sname)
                    state.ensure_pending(con, cur, f"bilby:{row_sname}")
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


def phase_bilby_children(
    portal_client: Any = None,
    gwc_client: Any = None,
    jc: Any = None,
    con: sqlite3.Connection | None = None,
):
    if gwc_client is None or jc is None:
        logger.info("phase_bilby_children: clients not wired - skipping")
        return
    logger.info("Starting phase_bilby_children")

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

        over_retry = set(state.failures_over(cur, settings.MAX_RETRY_ATTEMPTS))
        bytes_done = files_done = 0

        changed = set(state.get_changed_snames(cur))
        retry_snames = {
            key.split(":", 1)[1].split("/", 1)[0]
            for key in state.failures_under(cur, settings.MAX_RETRY_ATTEMPTS)
            if key.startswith("bilby:")
        }
        processing = sorted(changed | retry_snames)

        for sname in processing:
            state.ensure_pending(con, cur, f"bilby:{sname}")

        for sname in processing:
            try:
                detail = portal_client.get_superevent(sname)
            except Exception as e:
                logger.warning("failed to fetch detail for %s: %s", sname, e)
                state.record_failure(con, cur, f"bilby:{sname}", repr(e))
                continue

            linked: set[str] = set()
            try:
                job = gwc_client.get_gwflow_job(sname)
                if job is not None:
                    bilby_jobs = getattr(job, "bilby_jobs", None) or []
                    linked = {getattr(j, "gwflow_analysis_uid", "") for j in bilby_jobs}
                    linked.discard("")
            except Exception as e:
                logger.warning("failed to fetch linked jobs for %s: %s", sname, e)
                state.record_failure(con, cur, f"bilby:{sname}", repr(e))
                continue

            cluster_offline = False
            cap_reached = False
            for analysis in find_bilby_pe_analyses(detail):
                uid = analysis["uid"]
                key = f"{sname}/{uid}"
                fail_key = f"bilby:{sname}/{uid}"
                if uid in linked:
                    state.clear_failure(con, cur, fail_key)
                    continue
                if fail_key in over_retry:
                    continue

                state.ensure_pending(con, cur, fail_key)

                workdir = Path(settings.STAGING_DIR) / key
                archive = Path(settings.STAGING_DIR) / f"{key}.tar.gz"

                job_ref = state.get_failure_job_ref(cur, fail_key)
                try:
                    if job_ref is not None:
                        gwc_client.link_bilby_job_to_gwflow(job_ref, sname, uid)
                        state.clear_failure(con, cur, fail_key)
                    else:
                        ini_path = fetch_to_staging(jc, rec_for(analysis["config_file"], sname, uid))
                        ini_text = ini_path.read_text(encoding="utf-8")
                        results: list[Path] = []
                        for f in (analysis["result_file"], analysis["pesummary_result_file"]):
                            if f:
                                results.append(fetch_to_staging(jc, rec_for(f, sname, uid)))

                        if not settings.BACKFILL and (
                            files_done >= settings.MAX_FILES_PER_RUN or bytes_done >= settings.MAX_BYTES_PER_RUN
                        ):
                            cap_reached = True
                            break

                        name = f"{sname}--{uid}"
                        tree = synthesize_job_tree(workdir, name, ini_text, results)
                        make_archive(tree, archive)

                        job = gwc_client.upload_job_archive(
                            description=f"gwflow {sname} PE {uid}",
                            job_archive=archive,
                            public=True,
                        )
                        state.set_job_ref(con, cur, fail_key, str(job.id))
                        gwc_client.link_bilby_job_to_gwflow(job.id, sname, uid)

                        try:
                            ev = resolve_event_id_for(sname, detail)
                            if ev:
                                gwc_client.create_event_id(ev[0], ev[1], trigger_id=sname)
                                job.set_event_id(ev[0])
                        except Exception:
                            logger.warning("event id link failed for %s", key)

                        bytes_done += ini_path.stat().st_size + sum(r.stat().st_size for r in results)
                        files_done += 1
                        state.clear_failure(con, cur, fail_key)
                except ClusterOffline:
                    logger.warning("cluster offline - deferring remaining analyses")
                    cluster_offline = True
                    break
                except Exception as e:
                    state.record_failure(con, cur, fail_key, repr(e))
                finally:
                    shutil.rmtree(workdir, ignore_errors=True)
                    archive.unlink(missing_ok=True)

            if not cluster_offline and not cap_reached:
                remaining = [
                    k for k in state.failures_under(cur, settings.MAX_RETRY_ATTEMPTS) if k.startswith(f"bilby:{sname}/")
                ]
                if not remaining:
                    state.clear_failure(con, cur, f"bilby:{sname}")

            if cluster_offline or cap_reached:
                break

        logger.info("Completed phase_bilby_children")
    finally:
        if close_con and con:
            con.close()


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
        gwc = GWCloud(token=settings.GWCLOUD_TOKEN, endpoint=settings.GWCLOUD_ENDPOINT)
        jc = JobControllerClient(
            api_url=settings.JOB_CONTROLLER_API_URL,
            jwt_secret=settings.JOB_CONTROLLER_JWT_SECRET,
            user_id=0,
            cluster=settings.JOB_CONTROLLER_CLUSTER,
            bundle=settings.JOB_CONTROLLER_BUNDLE,
        )

        con = sqlite3.connect(settings.DB_PATH)
        con.row_factory = sqlite3.Row
        state.init_db(con)

        phase_metadata(gwc_client=gwc, con=con)
        phase_file_mirror(jc=jc, gwc_client=gwc, con=con)
        phase_bilby_children(gwc_client=gwc, jc=jc, con=con)

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
