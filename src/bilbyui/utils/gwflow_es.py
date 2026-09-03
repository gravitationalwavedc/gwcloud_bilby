import contextlib
import json
import logging

import elasticsearch
from django.conf import settings

logger = logging.getLogger(__name__)


class InvalidGWFlowMetadata(Exception):
    """Raised when portal metadata is not a valid strict-JSON top-level object."""


def _collect_review_statuses(metadata, job, path="", out=None):
    """
    Recursively collect scalar values under exact 'review_status' keys anywhere in
    metadata (objects or arrays). Deduplicated, preserving portal values.

    When an exact 'review_status' key holds an object or array value, it is not
    coerced or added; a structured warning is emitted and indexing continues.
    """
    if out is None:
        out = []

    if isinstance(metadata, dict):
        for key, value in metadata.items():
            child_path = f"{path}.{key}" if path else key
            if key == "review_status":
                if isinstance(value, (dict, list)):
                    logger.warning(
                        "Non-scalar review_status at %s for gwflow job %s (history %s); skipping",
                        child_path,
                        job.id,
                        getattr(job, "current_history_id", ""),
                    )
                else:
                    if value not in out:
                        out.append(value)
            else:
                _collect_review_statuses(value, job, child_path, out)
    elif isinstance(metadata, list):
        for index, value in enumerate(metadata):
            _collect_review_statuses(value, job, f"{path}[{index}]", out)

    return out


def parse_analyses(metadata: dict) -> list:
    """
    Parse analysis sections from gwflow portal metadata into a list of dicts.
    Defensive: never raises on malformed metadata.
    """
    analyses = []

    if not isinstance(metadata, dict):
        return analyses

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

    # Outer try keeps the "never raises on malformed metadata" guarantee for
    # section-level failures (e.g. a raising .items()); the inner per-record
    # try ensures one bad record does not abort parsing of later valid ones.
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

                try:
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
                            "deprecated": bool(item.get("deprecated", False)),
                            "analysts": analysts,
                            "reviewers": reviewers,
                        },
                    )
                except Exception as e:
                    logger.warning("Error parsing analysis record from gwflow metadata: %s", e)
    except Exception as e:
        logger.warning("Error parsing analyses from gwflow metadata: %s", e)

    return analyses


def build_gwflow_es_doc(job, metadata: dict) -> dict:
    """
    Build the ES document for a GWFlowJob from local fields + raw portal metadata.

    The document is a lossless pass-through: 'metadata' is the raw portal dict,
    copied directly (not traversed or reconstructed), and '_gwcloud' is a thin
    operational envelope containing only the seven approved fields.

    Raises InvalidGWFlowMetadata when metadata is not a valid payload, before any
    ES call.
    """
    if not isinstance(metadata, dict):
        raise InvalidGWFlowMetadata("metadata must be a top-level JSON object")

    # Strict JSON validation: rejects NaN/Infinity and non-JSON Python values.
    # RecursionError is translated to InvalidGWFlowMetadata so deeply nested
    # payloads follow the controlled failure path rather than escaping.
    try:
        serialized = json.dumps(metadata, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise InvalidGWFlowMetadata(f"metadata is not strict-JSON serializable: {exc}") from exc

    # The validated serialization round-trip is what is indexed.
    validated = json.loads(serialized)

    # Reject lossy round-trips (e.g. tuples -> lists, non-string dict keys ->
    # strings) so the indexed metadata is deeply equal to the input.
    if validated != metadata:
        raise InvalidGWFlowMetadata("metadata must contain only losslessly JSON-serialisable values")

    last_updated_time = (
        job.current_history_timestamp.isoformat() if getattr(job, "current_history_timestamp", None) else None
    )
    event_trigger_id = job.event_id.trigger_id if job.event_id else None

    try:
        review_statuses = _collect_review_statuses(validated, job)
    except RecursionError as exc:
        raise InvalidGWFlowMetadata("metadata is too deeply nested") from exc

    return {
        "_gwcloud": {
            "sname": job.sname,
            "libraries": job.libraries or [],
            "isPruned": job.is_pruned,
            "ligoOnly": job.ligo_only,
            "lastUpdatedTime": last_updated_time,
            "reviewStatuses": review_statuses,
            "eventTriggerId": event_trigger_id,
        },
        "metadata": validated,
    }


def get_es_client():
    return elasticsearch.Elasticsearch(
        hosts=[settings.ELASTIC_SEARCH_HOST],
        api_key=settings.ELASTIC_SEARCH_API_KEY,
        verify_certs=False,
    )


def gwflow_elastic_search_update(job, metadata: dict) -> None:
    """
    Upsert the doc (update, fall back to index). No-op if settings.IGNORE_ELASTIC_SEARCH.
    On InvalidGWFlowMetadata, logs an observable ingest failure and makes no ES call,
    leaving the existing ES document untouched.
    """
    if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
        return

    try:
        doc = build_gwflow_es_doc(job, metadata)
    except InvalidGWFlowMetadata as exc:
        logger.warning(
            "GWFlow ES ingest failed for job %s (history %s): %s",
            job.id,
            getattr(job, "current_history_id", ""),
            exc,
        )
        return

    es = get_es_client()

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

    es = get_es_client()

    with contextlib.suppress(elasticsearch.NotFoundError):
        es.delete(index=settings.ELASTIC_SEARCH_GWFLOW_INDEX, id=job.id)
