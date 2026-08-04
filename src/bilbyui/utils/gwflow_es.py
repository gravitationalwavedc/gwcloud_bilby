import logging

import elasticsearch
from django.conf import settings

logger = logging.getLogger(__name__)


def build_gwflow_es_doc(job, metadata: dict) -> dict:
    """
    Build the ES document for a GWFlowJob from local fields + portal metadata.
    Does not raise exceptions on missing metadata keys/sections.
    """
    if not isinstance(metadata, dict):
        logger.warning("gwflow ES doc builder received non-dict metadata: %r", type(metadata))
        metadata = {}

    # User display name
    user_name = ""
    if job.user:
        user_name = getattr(job.user, "name", None) or ""
        if not user_name:
            first = getattr(job.user, "first_name", "") or ""
            last = getattr(job.user, "last_name", "") or ""
            user_name = f"{first} {last}".strip() or getattr(job.user, "username", "") or ""

    # Event ID dict
    event_id_doc = None
    if job.event_id:
        event_id_doc = {
            "eventId": getattr(job.event_id, "event_id", ""),
            "triggerId": getattr(job.event_id, "trigger_id", ""),
            "nickname": getattr(job.event_id, "nickname", ""),
            "gpsTime": getattr(job.event_id, "gps_time", 0.0),
        }

    # Datetime ISO formatting
    current_history_ts = (
        job.current_history_timestamp.isoformat() if getattr(job, "current_history_timestamp", None) else None
    )
    creation_time_str = job.creation_time.isoformat() if getattr(job, "creation_time", None) else None
    last_updated_str = job.last_updated.isoformat() if getattr(job, "last_updated", None) else None

    # Defensive analysis parsing
    analyses = []

    # Map analysis sections to their ES type name
    section_type_map = {
        "ParameterEstimation": "pe",
        "parameter_estimation": "pe",
        "pe": "pe",
        "TGR": "tgr",
        "tgr": "tgr",
        "Lensing": "lensing",
        "lensing": "lensing",
        "Matter": "matter",
        "matter": "matter",
        "Cosmology": "cosmology",
        "cosmology": "cosmology",
        "RNP": "rnp",
        "rnp": "rnp",
    }

    try:
        for section_key, section_data in metadata.items():
            if section_key not in section_type_map:
                continue

            analysis_type = section_type_map[section_key]

            # section_data may be a list of dicts, or a dict of items, or a single dict
            items = []
            if isinstance(section_data, list):
                items = section_data
            elif isinstance(section_data, dict):
                # If section_data is a dict containing a 'results' list, use that
                if "results" in section_data and isinstance(section_data["results"], list):
                    items = section_data["results"]
                else:
                    items = [section_data]

            for item in items:
                if not isinstance(item, dict):
                    continue

                # Parse analysts / reviewers as lists of strings
                raw_analysts = item.get("analysts") or []
                if isinstance(raw_analysts, list):
                    analysts = [a.get("name") if isinstance(a, dict) else str(a) for a in raw_analysts if a]
                else:
                    analysts = [str(raw_analysts)]

                raw_reviewers = item.get("reviewers") or []
                if isinstance(raw_reviewers, list):
                    reviewers = [r.get("name") if isinstance(r, dict) else str(r) for r in raw_reviewers if r]
                else:
                    reviewers = [str(raw_reviewers)]

                analyses.append(
                    {
                        "uid": str(item.get("uid") or item.get("id") or ""),
                        "type": analysis_type,
                        "software": str(item.get("inference_software") or item.get("software") or ""),
                        "waveform": str(item.get("waveform_approximant") or item.get("waveform") or ""),
                        "runStatus": str(item.get("run_status") or ""),
                        "reviewStatus": str(item.get("review_status") or ""),
                        "analysts": analysts,
                        "reviewers": reviewers,
                    }
                )
    except Exception as e:
        logger.warning("Error parsing analyses from gwflow metadata for job %s: %s", job.id, e)

    # GraceDB section
    gracedb_doc = {
        "uids": [],
        "gpsTime": "",
        "far": "",
        "instruments": "",
    }

    try:
        gracedb_section = metadata.get("GraceDB") or metadata.get("gracedb") or {}
        if isinstance(gracedb_section, dict):
            events = gracedb_section.get("Events") or gracedb_section.get("events") or []
            if isinstance(events, list):
                uids = []
                for ev in events:
                    if isinstance(ev, dict):
                        uid = ev.get("uid") or ev.get("id") or ev.get("name")
                        if uid:
                            uids.append(str(uid))
                    elif isinstance(ev, str):
                        uids.append(ev)
                gracedb_doc["uids"] = uids

            gracedb_doc["gpsTime"] = str(
                gracedb_section.get("preferred_event_gps") or gracedb_section.get("gps_time") or ""
            )
            gracedb_doc["far"] = str(gracedb_section.get("preferred_event_far") or gracedb_section.get("far") or "")
            gracedb_doc["instruments"] = str(gracedb_section.get("instruments") or "")
    except Exception as e:
        logger.warning("Error parsing GraceDB from gwflow metadata for job %s: %s", job.id, e)

    # Child Bilby jobs IDs
    child_job_ids = []
    if hasattr(job, "bilby_jobs"):
        child_job_ids = list(job.bilby_jobs.values_list("id", flat=True))

    return {
        "user": {"name": user_name},
        "sname": job.sname,
        "schemaVersion": job.schema_version,
        "libraries": job.libraries or [],
        "isPruned": job.is_pruned,
        "ligoOnly": job.ligo_only,
        "eventId": event_id_doc,
        "currentHistoryId": job.current_history_id,
        "currentHistoryTimestamp": current_history_ts,
        "creationTime": creation_time_str,
        "lastUpdatedTime": last_updated_str,
        "analyses": analyses,
        "gracedb": gracedb_doc,
        "childJobIds": child_job_ids,
    }


def _get_es_client():
    return elasticsearch.Elasticsearch(
        hosts=[settings.ELASTIC_SEARCH_HOST],
        api_key=settings.ELASTIC_SEARCH_API_KEY,
        verify_certs=False,
    )


def gwflow_elastic_search_update(job, metadata: dict) -> None:
    """
    Upsert the doc (update, fall back to index). No-op if settings.IGNORE_ELASTIC_SEARCH.
    Mirrors BilbyJob.elastic_search_update.
    """
    if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
        return

    es = _get_es_client()

    doc = build_gwflow_es_doc(job, metadata)

    try:
        es.update(index=settings.ELASTIC_SEARCH_GWFLOW_INDEX, id=job.id, doc=doc)
    except elasticsearch.NotFoundError:
        es.index(index=settings.ELASTIC_SEARCH_GWFLOW_INDEX, id=job.id, document=doc)


def gwflow_elastic_search_remove(job) -> None:
    """
    Delete the doc; swallow NotFoundError. No-op if IGNORE_ELASTIC_SEARCH.
    """
    if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
        return

    es = _get_es_client()

    try:
        es.delete(index=settings.ELASTIC_SEARCH_GWFLOW_INDEX, id=job.id)
    except elasticsearch.NotFoundError:
        pass


def update_child_job_ids(job) -> None:
    """
    Perform a targeted update of childJobIds in Elasticsearch for a GWFlowJob.
    No-op if settings.IGNORE_ELASTIC_SEARCH. Swallow NotFoundError if document is not in ES yet.
    """
    if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
        return

    es = _get_es_client()

    child_job_ids = list(job.bilby_jobs.values_list("id", flat=True))

    try:
        es.update(
            index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
            id=job.id,
            doc={"childJobIds": child_job_ids},
        )
    except elasticsearch.NotFoundError:
        pass

