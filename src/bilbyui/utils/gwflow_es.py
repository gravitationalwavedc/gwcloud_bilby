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
        job.current_history_timestamp.isoformat()
        if getattr(job, "current_history_timestamp", None)
        else None
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
