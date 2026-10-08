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
from gwdc_python.exceptions import GWDCUnknownException

import settings
import state
from bilby_children import (
    Rejection,
    StageError,
    _is_truthy_preferred,
    _tree_relative_target,
    make_archive,
    resolve_event_id_for,
    resolve_missing_path,
    select_bilby_analyses,
    stage_supporting_files,
    synthesize_job_tree,
    validate_supported_software,
)
from fetch import _get, fetch_to_staging
from job_controller import ClusterOffline, JobControllerClient
from libraries import normalise_libraries
from portal import PortalClient, PortalMalformedResponseError

_LINKED_JOBS_QUERY = "{ gwflowLinkedBilbyJobs(sname: $sname) { id gwflowAnalysisUid } }"


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


class _AnalysisAborted(Exception):
    """Internal sentinel: the analysis was already recorded as failed; skip upload."""


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


def resolve_libraries(portal_client: Any, sname: str, detail: Any = None) -> list | None:
    """Resolve library names for a superevent from the portal /versions/ endpoint.

    Returns:
      - a list of normalised library names to set,
      - [] to clear libraries (no current version, or explicit empty),
      - None to leave libraries unchanged (endpoint failure / malformed data).
    """
    try:
        versions = portal_client.get_versions(sname)
    except Exception as e:
        logger.warning("Failed to fetch versions for %s: %s", sname, e)
        return None

    if not isinstance(versions, list):
        logger.warning("Non-list versions payload for %s", sname)
        return None

    current = [v for v in versions if isinstance(v, dict) and _is_truthy_preferred(v.get("is_current"))]
    if len(current) > 1:
        logger.warning("Multiple current versions for %s; using first", sname)

    if not current:
        # No current version: clear libraries for non-pruned jobs (the metadata
        # phase only processes non-pruned changed rows).
        return []

    # The current version's libraries member must be a list. Any other shape
    # (string, mapping, scalar, missing, or null) is malformed: preserve the
    # existing stored libraries (return None) rather than normalising a
    # generic iterable into a corrupt or empty authoritative value.
    raw_libraries = current[0].get("libraries")
    if not isinstance(raw_libraries, list):
        detail_libraries = detail.get("libraries") if isinstance(detail, dict) else None
        if not isinstance(detail_libraries, list):
            logger.warning("Malformed libraries payload for %s", sname)
            return None
        raw_libraries = detail_libraries
    return normalise_libraries(raw_libraries)


def phase_metadata(
    portal_client: Any = None,
    gwc_client: Any = None,
    con: sqlite3.Connection | None = None,
) -> list[Rejection]:
    logger.info("Starting phase_metadata")
    rejections: list[Rejection] = []

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
                row_ts = row.get("record_timestamp")
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
                        rejection = Rejection(
                            sname=row_sname,
                            analysis_uid=None,
                            role=None,
                            available_file_systems=(),
                            reason="non-dict superevent detail",
                        )
                        rejections.append(rejection)
                        logger.error(
                            "Rejected superevent detail sname=%s reason=%s",
                            row_sname,
                            rejection.reason,
                        )
                        state.record_failure(con, cur, row_sname, rejection.reason)
                        has_failure_in_run = True
                        continue
                    libraries = resolve_libraries(portal_client, row_sname, detail)
                    metadata = detail.get("raw_payload", {})
                    if not isinstance(metadata, dict):
                        metadata = {}

                    if gwc_client is not None:
                        ev = resolve_event_id_for(row_sname, detail)
                        if ev:
                            try:
                                gwc_client.create_event_id(ev[0], ev[1], trigger_id=row_sname)
                            except Exception as e:
                                logger.warning("create_event_id failed for superevent %s: %s", row_sname, e)

                        gwc_client.upsert_gwflow_job(
                            sname=row_sname,
                            event_id=row_sname,
                            schema_version=row_schema_ver,
                            metadata=metadata,
                            libraries=libraries,
                            is_pruned=False,
                            current_history_id=row_commit_sha,
                            current_history_timestamp=row_ts,
                        )

                    state.clear_failure(con, cur, row_sname)
                    state.record_changed_sname(con, cur, row_sname)
                    state.ensure_pending(con, cur, f"bilby:{row_sname}")
                    if not has_failure_in_run:
                        state.set_watermark(con, cur, row_ts)
                        state.set_last_sname(con, cur, row_sname)

                except PortalMalformedResponseError as e:
                    rejection = Rejection(
                        sname=row_sname,
                        analysis_uid=None,
                        role=None,
                        available_file_systems=(),
                        reason=str(e),
                    )
                    rejections.append(rejection)
                    logger.error(
                        "Malformed superevent detail sname=%s reason=%s",
                        row_sname,
                        rejection.reason,
                    )
                    state.record_failure(con, cur, row_sname, rejection.reason)
                    if state.get_failure_count(cur, row_sname) >= settings.MAX_RETRY_ATTEMPTS:
                        logger.exception("giving up on %s", row_sname)
                    else:
                        has_failure_in_run = True
                    continue
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

    finally:
        if close_con and con:
            con.close()

    logger.info("Completed phase_metadata")
    return rejections


def linked_analysis_uids(gwc_client, sname):
    """Return the set of analysis uids already linked to sname.

    Uses the ingest-only, unscoped gwflowLinkedBilbyJobs lookup so a child the
    ingest user cannot see through the visibility-filtered gwflowJobBySname
    query is still matched, preventing a duplicate child upload.
    """
    data = gwc_client.request(query=_LINKED_JOBS_QUERY, variables={"sname": sname})
    return {row["gwflow_analysis_uid"] for row in data["gwflow_linked_bilby_jobs"]}


def phase_bilby_children(
    portal_client: Any = None,
    gwc_client: Any = None,
    jc: Any = None,
    con: sqlite3.Connection | None = None,
) -> list[Rejection]:
    if gwc_client is None or jc is None:
        logger.info("phase_bilby_children: clients not wired - skipping")
        return []
    logger.info("Starting phase_bilby_children")
    rejections: list[Rejection] = []

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
            except PortalMalformedResponseError as e:
                rejection = Rejection(
                    sname=sname,
                    analysis_uid=None,
                    role=None,
                    available_file_systems=(),
                    reason=str(e),
                )
                rejections.append(rejection)
                logger.error(
                    "Malformed superevent detail sname=%s reason=%s",
                    sname,
                    rejection.reason,
                )
                state.record_failure(con, cur, rejection.fail_key, rejection.reason)
                continue
            except Exception as e:
                logger.warning("failed to fetch detail for %s: %s", sname, e)
                state.record_failure(con, cur, f"bilby:{sname}", repr(e))
                continue

            try:
                linked = linked_analysis_uids(gwc_client, sname)
            except Exception as e:
                logger.warning("failed to fetch linked jobs for %s: %s", sname, e)
                state.record_failure(con, cur, f"bilby:{sname}", repr(e))
                continue

            cluster_offline = False
            cap_reached = False
            analyses, selection_rejections = select_bilby_analyses(
                sname,
                detail,
                settings.ACCESSIBLE_FILE_SYSTEMS,
            )
            rejections.extend(selection_rejections)
            for rejection in selection_rejections:
                logger.error(
                    "Rejected Bilby analysis sname=%s uid=%s role=%s available_file_systems=%s reason=%s",
                    rejection.sname,
                    rejection.analysis_uid,
                    rejection.role,
                    rejection.available_file_systems,
                    rejection.reason,
                )
                state.record_failure(
                    con,
                    cur,
                    rejection.fail_key,
                    rejection.reason,
                )

            for analysis in analyses:
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

                        result_file_path = None
                        rf = analysis.get("result_file")
                        if isinstance(rf, dict) and rf.get("path"):
                            result_file_path = rf["path"]

                        try:
                            job = gwc_client.upload_job_archive(
                                description=f"gwflow {sname} PE {uid}",
                                job_archive=archive,
                                public=True,
                            )
                        except GWDCUnknownException as e:
                            extensions = getattr(e, "extensions", None) or {}
                            missing_files = extensions.get("missing_files") or []
                            if not missing_files:
                                raise
                            seen: set[str] = set()
                            missing: list[str] = []
                            for p in missing_files:
                                if p not in seen:
                                    seen.add(p)
                                    missing.append(p)
                            staged_files: dict[str, Path] = {}
                            for p in missing:
                                # Validate the tree-relative destination before
                                # any fetch so a reserved or unsafe path is
                                # rejected without mutating the tree.
                                try:
                                    _tree_relative_target(p)
                                except StageError as target_err:
                                    state.record_failure(con, cur, fail_key, repr(target_err))
                                    raise _AnalysisAborted() from target_err
                                resolved = resolve_missing_path(p, ini_text, result_file_path)
                                if resolved is None:
                                    state.record_failure(con, cur, fail_key, f"unresolvable missing path {p!r}")
                                    raise _AnalysisAborted()
                                try:
                                    fetched = fetch_to_staging(jc, rec_for({"path": resolved}, sname, uid))
                                except Exception as fetch_err:
                                    state.record_failure(con, cur, fail_key, repr(fetch_err))
                                    raise _AnalysisAborted() from fetch_err
                                staged_files[p] = fetched
                            try:
                                stage_supporting_files(tree, missing, staged_files)
                            except StageError as se:
                                state.record_failure(con, cur, fail_key, repr(se))
                                raise _AnalysisAborted() from se
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
                        except Exception as e:
                            logger.warning("event id creation failed for %s: %s", key, e)

                        bytes_done += ini_path.stat().st_size + sum(r.stat().st_size for r in results)
                        files_done += 1
                        state.clear_failure(con, cur, fail_key)
                except ClusterOffline:
                    logger.warning("cluster offline - deferring remaining analyses")
                    cluster_offline = True
                    break
                except _AnalysisAborted:
                    pass
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

    return rejections


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
            key = None
            staged = None
            try:
                analysis_uid = _get(rec, "analysis_uid") or ""
                key = f"{_get(rec, 'sname')}/{analysis_uid}/{_get(rec, 'path')}"
                if key in over_retry:
                    continue
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
    validate_supported_software()

    lock_path = Path(settings.LOCK_PATH) if settings.LOCK_PATH else Path(settings.DB_PATH).with_suffix(".lock")
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

        rejections = []
        rejections.extend(phase_metadata(gwc_client=gwc, con=con))
        rejections.extend(phase_file_mirror(jc=jc, gwc_client=gwc, con=con) or [])
        rejections.extend(phase_bilby_children(gwc_client=gwc, jc=jc, con=con))

        con.close()
        logger.info("Completed gwflow_ingest run")
        return 1 if rejections else 0
    finally:
        if lock_file:
            with contextlib.suppress(OSError):
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


if __name__ == "__main__":
    sys.exit(run())
