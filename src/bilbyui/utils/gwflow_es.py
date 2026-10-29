import contextlib
import hashlib
import json
import logging

import elasticsearch
from django.conf import settings
from django.core.cache import caches

from bilbyui.utils.search_trigger_time import max_finite_time

logger = logging.getLogger(__name__)


class InvalidGWFlowMetadata(Exception):
    """Raised when portal metadata is not a valid strict-JSON top-level object."""


def _parse_portal_bool(value) -> bool:
    """Normalise a portal boolean-like value to a real bool.

    Portal payloads may carry boolean fields as strings (e.g. ``"true"`` /
    ``"false"``), so a bare ``bool()`` would misclassify any non-empty string
    as truthy. Treat ``"true"/"1"/"yes"`` (case-insensitive) as true and
    everything else as false. This is a case-insensitive superset of the
    cron-side ``_TRUTHY_PREFERRED`` tuple (which is case-sensitive and does
    not include ``"1"``).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


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
                        getattr(job, "current_version_number", None),
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
    """Return the canonical analyses of a portal detail payload.

    Consumes only ``metadata["analyses"]``. An absent member yields ``[]``;
    a present null or any other non-array value is malformed and rejected, as
    required at the GWF-1 boundary. Every present entry must be an object
    carrying the required canonical fields; a malformed entry fails the whole
    source record (``InvalidGWFlowMetadata``) rather than being skipped or
    defaulted.
    """
    if not isinstance(metadata, dict):
        raise InvalidGWFlowMetadata("metadata must be a top-level JSON object")

    if "analyses" not in metadata:
        return []
    if metadata["analyses"] is None:
        raise InvalidGWFlowMetadata("metadata.analyses must be an array")

    raw_analyses = metadata["analyses"]
    if not isinstance(raw_analyses, list):
        raise InvalidGWFlowMetadata("metadata.analyses must be an array")

    analyses = []
    for index, entry in enumerate(raw_analyses):
        analyses.append(_parse_analysis(entry, index))
    return analyses


_ANALYSIS_STATUSES = frozenset({"complete", "running", "stuck", "unstarted", "cancelled"})
_REVIEW_STATUSES = frozenset({"pending", "approved", "rejected"})
_ANALYSIS_REQUIRED = (
    "uid",
    "type",
    "revision",
    "name",
    "description",
    "status",
    "deprecated",
    "software",
    "analysts",
    "reviews",
    "input_files",
    "output_files",
    "configurations",
)


def _parse_analysis(entry, index):
    where = f"metadata.analyses[{index}]"
    if not isinstance(entry, dict):
        raise InvalidGWFlowMetadata(f"{where} must be an object")

    missing = [field for field in _ANALYSIS_REQUIRED if field not in entry]
    if missing:
        raise InvalidGWFlowMetadata(f"{where} is missing required field(s): {', '.join(missing)}")

    uid = entry["uid"]
    if not isinstance(uid, str) or not uid.strip():
        raise InvalidGWFlowMetadata(f"{where}.uid must be a non-empty string")

    analysis_type = entry["type"]
    if analysis_type not in ("pe", "event_validation"):
        raise InvalidGWFlowMetadata(f"{where}.type must be 'pe' or 'event_validation'")

    status = entry["status"]
    if status not in _ANALYSIS_STATUSES:
        raise InvalidGWFlowMetadata(f"{where}.status is not a canonical status: {status!r}")

    if not isinstance(entry["deprecated"], bool):
        raise InvalidGWFlowMetadata(f"{where}.deprecated must be a boolean")

    revision = entry["revision"]
    if isinstance(revision, bool) or not isinstance(revision, (int, str)):
        raise InvalidGWFlowMetadata(f"{where}.revision must be an integer or a string")

    for field in ("name", "description"):
        if not isinstance(entry[field], str):
            raise InvalidGWFlowMetadata(f"{where}.{field} must be a string")

    for field in ("analysts", "reviews", "input_files", "output_files", "configurations"):
        if not isinstance(entry[field], list):
            raise InvalidGWFlowMetadata(f"{where}.{field} must be an array")

    software = entry["software"]
    if software is not None:
        if not isinstance(software, dict):
            raise InvalidGWFlowMetadata(f"{where}.software must be an object or null")
        for field in ("name", "version"):
            if not isinstance(software.get(field), str):
                raise InvalidGWFlowMetadata(f"{where}.software.{field} must be a string")

    if analysis_type == "pe":
        if not isinstance(entry.get("in_catalog"), bool):
            raise InvalidGWFlowMetadata(f"{where}.in_catalog must be a boolean for a pe analysis")
    else:
        suggested = entry.get("suggested_detector_configuration_uids")
        if not isinstance(suggested, list):
            raise InvalidGWFlowMetadata(
                f"{where}.suggested_detector_configuration_uids must be an array for an event_validation analysis"
            )

    reviews = []
    for review_index, review in enumerate(entry["reviews"]):
        if not isinstance(review, dict):
            raise InvalidGWFlowMetadata(f"{where}.reviews[{review_index}] must be an object")
        review_status = review.get("review_status")
        if review_status is not None and review_status not in _REVIEW_STATUSES:
            raise InvalidGWFlowMetadata(f"{where}.reviews[{review_index}].review_status is not canonical")
        reviews.append(review)

    review_status = entry.get("review_status")
    if review_status is None:
        statuses = [review.get("review_status") for review in reviews]
        if statuses and all(value == "approved" for value in statuses):
            review_status = "approved"
        elif "rejected" in statuses:
            review_status = "rejected"
        else:
            review_status = "pending"
    elif review_status not in _REVIEW_STATUSES:
        raise InvalidGWFlowMetadata(f"{where}.review_status is not canonical: {review_status!r}")

    return {
        "uid": uid,
        "type": analysis_type,
        "revision": entry["revision"],
        "name": entry["name"],
        "description": entry["description"],
        "status": status,
        "review_status": review_status,
        "software": software,
        "deprecated": entry["deprecated"],
        "analysts": entry["analysts"],
        "reviews": reviews,
        "input_files": entry["input_files"],
        "output_files": entry["output_files"],
        "configurations": entry["configurations"],
        "in_catalog": entry.get("in_catalog") if analysis_type == "pe" else False,
        "suggested_detector_configuration_uids": (
            entry.get("suggested_detector_configuration_uids") if analysis_type == "event_validation" else []
        ),
    }


def build_gwflow_es_doc(job, metadata: dict) -> dict:
    """
    Build the ES document for a GWFlowJob from local fields + raw portal metadata.

    The document is a lossless pass-through: 'metadata' is the raw portal dict,
    copied directly (not traversed or reconstructed), and '_gwcloud' is a thin
    operational envelope containing only the approved fields.

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
        # The validated serialization round-trip is what is indexed.
        validated = json.loads(serialized)
    except (TypeError, ValueError, RecursionError) as exc:
        raise InvalidGWFlowMetadata(f"metadata is not strict-JSON serializable: {exc}") from exc

    # Validate the canonical analyses boundary before the raw, lossless payload
    # is submitted to Elasticsearch. Absent/null analyses remain valid, while
    # any malformed present entry rejects the whole source record.
    parse_analyses(validated)

    # Reject lossy round-trips (e.g. tuples -> lists, non-string dict keys ->
    # strings) so the indexed metadata is deeply equal to the input.
    if validated != metadata:
        raise InvalidGWFlowMetadata("metadata must contain only losslessly JSON-serialisable values")

    last_updated_time = (
        job.current_history_timestamp.isoformat() if getattr(job, "current_history_timestamp", None) else None
    )
    event_trigger_id = job.event_id.trigger_id if job.event_id else None
    search_trigger_time = max_finite_time(
        (
            job.trigger_time,
            job.event_id.gps_time if job.event_id else None,
        )
    )

    try:
        review_statuses = _collect_review_statuses(validated, job)
    except RecursionError as exc:
        raise InvalidGWFlowMetadata("metadata is too deeply nested") from exc

    envelope = {
        "sname": job.sname,
        "libraries": job.libraries or [],
        "isPruned": job.is_pruned,
        "lastUpdatedTime": last_updated_time,
        "reviewStatuses": review_statuses,
        "eventTriggerId": event_trigger_id,
    }
    if search_trigger_time is not None:
        envelope["searchTriggerTime"] = search_trigger_time

    return {
        "_gwcloud": envelope,
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
            getattr(job, "current_version_number", None),
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


def eligible_gwflow_jobs():
    """Return every local GWFlowJob in stable primary-key order.

    The complete eligible set is the population driver for an index rebuild:
    all rows, including pruned ones, because ``isPruned`` is an indexed field.
    """
    from bilbyui.models import GWFlowJob

    return GWFlowJob.objects.select_related("event_id").order_by("pk")


_GWFLOW_NUMERIC_TEMPLATE_SECTIONS = (
    ("analyses_numbers", "metadata.analyses"),
    ("detector_configuration_numbers", "metadata.detector_configurations"),
    ("gracedb_event_numbers", "metadata.gracedb_events"),
    ("catalog_connection_numbers", "metadata.catalog_connections"),
)


def build_gwflow_es_mapping():
    """Return the authoritative mapping body for the GWFlow index.

    Numeric leaves under the four canonical metadata collections map to
    ``double`` for both integer and floating-point JSON inputs, so a field
    observed as a long in one document and a double in another cannot fail
    because of document order. Nothing is mapped ``nested``.
    """
    templates = [
        {
            f"{name}_{json_type}": {
                "path_match": f"{section}.*",
                "match_mapping_type": json_type,
                "mapping": {"type": "double"},
            }
        }
        for name, section in _GWFLOW_NUMERIC_TEMPLATE_SECTIONS
        for json_type in ("long", "double")
    ]

    from bilbyui.services.search_registry import _DEFAULT_FIELD, GWFLOW_ALIASES

    return {
        "settings": {"index": {"query": {"default_field": _DEFAULT_FIELD}}},
        "mappings": {
            "dynamic_templates": templates,
            "properties": {
                **{alias: {"type": "alias", "path": target} for alias, target in GWFLOW_ALIASES.items()},
                "_gwcloud": {
                    "type": "object",
                    "dynamic": "strict",
                    "properties": {
                        "sname": {"type": "keyword"},
                        "libraries": {"type": "keyword"},
                        "isPruned": {"type": "boolean"},
                        "lastUpdatedTime": {
                            "type": "date",
                            "format": "strict_date_optional_time||epoch_millis",
                        },
                        "reviewStatuses": {"type": "keyword"},
                        "eventTriggerId": {"type": "keyword"},
                        "searchTriggerTime": {"type": "double"},
                    },
                },
                "metadata": {
                    "type": "object",
                    "dynamic": True,
                    "properties": {
                        "analyses": {
                            "type": "object",
                            "properties": {
                                "uid": {"type": "keyword"},
                                "type": {"type": "keyword"},
                                "status": {"type": "keyword"},
                                "review_status": {"type": "keyword"},
                                "deprecated": {"type": "boolean"},
                                "software": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "keyword"},
                                        "version": {"type": "keyword"},
                                    },
                                },
                                "configurations": {"type": "object"},
                            },
                        },
                        "detector_configurations": {
                            "type": "object",
                            "properties": {"uid": {"type": "keyword"}},
                        },
                        "gracedb_events": {
                            "type": "object",
                            "properties": {
                                "network_snr": {"type": "double"},
                                "far": {"type": "double"},
                                "pipeline": {"type": "keyword"},
                            },
                        },
                        "catalog_connections": {"type": "object"},
                        # Legacy O4 payload retained in _source for provenance but
                        # deliberately not indexed: its loose date/number formats
                        # collide with dynamically inferred mappings.
                        "raw_payload": {"type": "object", "enabled": False},
                    },
                },
            },
        },
    }


_DEFAULT_DATE_FORMAT = "strict_date_optional_time||epoch_millis"


def _normalise_dynamic(value):
    """Normalise ES's stringified booleans for comparison."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return value


def mapping_satisfies_contract(expected, actual):
    """Return True when ``actual`` contains every declaration in ``expected``.

    Elasticsearch expands dynamic mappings, adds fields inferred from indexed
    documents, and normalises some values (``dynamic: true`` comes back as
    ``"true"``; a date using the default format omits ``format``). Comparing
    the whole installed mapping for equality therefore always fails on a real
    cluster. This checks that every explicitly declared property and template
    is present and correct, ignoring fields ES inferred on its own.
    """
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False

    for key, expected_value in expected.items():
        if (
            key == "type"
            and expected_value == "object"
            and key not in actual
            and isinstance(actual.get("properties"), dict)
        ):
            # ES omits the implied type for an object that declares properties.
            continue
        if (
            key == "format"
            and key not in actual
            and expected.get("type") == "date"
            and expected_value == _DEFAULT_DATE_FORMAT
        ):
            continue
        if key not in actual:
            return False
        actual_value = actual[key]

        if key == "properties":
            if not isinstance(actual_value, dict) or not isinstance(expected_value, dict):
                return False
            for prop, prop_expected in expected_value.items():
                if prop not in actual_value:
                    return False
                if not mapping_satisfies_contract(prop_expected, actual_value[prop]):
                    return False
            continue
        if key == "dynamic_templates":
            if actual_value != expected_value:
                return False
            continue
        if key == "dynamic":
            if _normalise_dynamic(expected_value) != _normalise_dynamic(actual_value):
                return False
            continue

        if isinstance(expected_value, dict):
            if not mapping_satisfies_contract(expected_value, actual_value):
                return False
        elif expected_value != actual_value:
            return False

    return True


def compute_protected_identity_digest():
    """Return per-model digests of the protected row identities.

    Read-only: it never creates, updates or deletes a row. Each tuple is
    (pk, owner id, critical foreign-key ids) in primary-key order, so any
    created, deleted, re-keyed, re-owned or re-linked row changes its digest.
    """
    from bilbyui.models import BilbyJob, EventID, ExternalBilbyJob, GWFlowJob

    specs = {
        "GWFlowJob": (GWFlowJob, ("id", "user_id", "event_id_id")),
        "BilbyJob": (BilbyJob, ("id", "user_id", "event_id_id", "gwflow_job_id", "job_controller_id")),
        "ExternalBilbyJob": (ExternalBilbyJob, ("id", "job_id")),
        "EventID": (EventID, ("id",)),
    }

    digests = {}
    combined = []
    for name, (model, fields) in specs.items():
        rows = list(model.objects.order_by("pk").values_list(*fields))
        payload = json.dumps(rows, default=str, separators=(",", ":"))
        digests[name] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        combined.append(f"{name}:{digests[name]}")

    digests["combined"] = hashlib.sha256("|".join(combined).encode("utf-8")).hexdigest()
    return digests


def clear_gwflow_portal_cache(sname) -> None:
    """Drop the cached current-detail entry so a rebuild reads live data."""
    caches["default"].delete(f"gwflow:se:{sname}")


def invalidate_gwflow_facet_caches() -> None:
    """Invalidate filter-option caches that mirror index contents."""
    from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY

    cache = caches["default"]
    cache.delete(LIBRARIES_CACHE_KEY)
    cache.delete(REVIEW_STATUSES_CACHE_KEY)
