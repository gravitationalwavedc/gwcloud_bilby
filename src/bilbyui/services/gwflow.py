import logging
from datetime import datetime, timedelta

import elasticsearch
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from bilbyui.models import GWFlowJob
from bilbyui.services.jobs import _extract_es_total, _numeric_es_records, _time_range_to_timedelta
from bilbyui.utils.gwflow_es import get_es_client
from bilbyui.utils.misc import is_ligo_user

logger = logging.getLogger(__name__)

LIBRARIES_CACHE_KEY = "gwflow_filter_libraries"
REVIEW_STATUSES_CACHE_KEY = "gwflow_filter_review_statuses"
FILTER_OPTIONS_TTL = 24 * 60 * 60
FRESH_OPTIONS_TTL = 60 * 60

_ES_ERRORS = (elasticsearch.exceptions.TransportError, elasticsearch.exceptions.ApiError)

# Centralised visibility/pruning clauses shared by result retrieval and both
# facet aggregations so the field names cannot drift.
_GWCLOUD_LIGO_ONLY_FILTER = {"term": {"_gwcloud.ligoOnly": False}}
_GWCLOUD_PRUNED_FILTER = {"term": {"_gwcloud.isPruned": False}}


def _public_visibility_filters():
    """Public, non-pruned visibility clauses used by both facet aggregations."""
    return [_GWCLOUD_PRUNED_FILTER, _GWCLOUD_LIGO_ONLY_FILTER]


def _collect_library_options():
    es = get_es_client()
    results = es.search(
        index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
        query={"bool": {"filter": _public_visibility_filters()}},
        size=0,
        aggs={
            "libraries": {
                "terms": {"field": "_gwcloud.libraries", "size": 50},
            }
        },
    )
    buckets = results.get("aggregations", {}).get("libraries", {}).get("buckets", [])
    return [bucket.get("key") for bucket in buckets if isinstance(bucket, dict) and bucket.get("key")]


def _collect_review_status_options():
    es = get_es_client()
    results = es.search(
        index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
        query={"bool": {"filter": _public_visibility_filters()}},
        size=0,
        aggs={
            "review_statuses": {
                "terms": {"field": "_gwcloud.reviewStatuses", "size": 50},
            }
        },
    )
    buckets = results.get("aggregations", {}).get("review_statuses", {}).get("buckets", [])
    return [bucket.get("key") for bucket in buckets if isinstance(bucket, dict) and bucket.get("key")]


def _parse_cache_record(record):
    """Normalise a cached filter-option record to (values, fetched_at).

    Tolerates legacy plain-list records (the old format) by treating them as a
    fresh result. Returns (None, None) when the record is absent or malformed.
    """
    if record is None:
        return None, None
    if isinstance(record, list):
        return record, timezone.now()
    if isinstance(record, dict) and "values" in record:
        return record.get("values"), record.get("fetched_at")
    return None, None


def _is_fresh(fetched_at):
    if not isinstance(fetched_at, datetime):
        return False
    if fetched_at.tzinfo is None:
        fetched_at = timezone.make_aware(fetched_at)
    return timezone.now() - fetched_at <= timedelta(seconds=FRESH_OPTIONS_TTL)


def _facet_options(cache_key, collect):
    """Shared freshness/cache evaluator for one filter-option facet.

    Returns {"values": [...], "state": "ok"|"stale"|"unavailable"}.
    """
    record = cache.get(cache_key)
    cached_values, fetched_at = _parse_cache_record(record)

    if cached_values is not None and _is_fresh(fetched_at):
        return {"values": cached_values, "state": "ok"}

    try:
        values = collect()
    except _ES_ERRORS:
        logger.exception("Failed to refresh %s filter options from Elasticsearch", cache_key)
        if cached_values is not None:
            return {"values": cached_values, "state": "stale"}
        return {"values": [], "state": "unavailable"}

    cache.set(cache_key, {"values": values, "fetched_at": timezone.now()}, FILTER_OPTIONS_TTL)
    return {"values": values, "state": "ok"}


def list_gwflow_filter_options():
    """Return per-facet filter options for the GWFlow job list surface.

    Each facet is evaluated independently with its own ok/stale/unavailable
    state, backed by a per-facet cache record ({values, fetched_at}, 24h TTL).
    """
    return {
        "libraries": _facet_options(LIBRARIES_CACHE_KEY, _collect_library_options),
        "review_statuses": _facet_options(REVIEW_STATUSES_CACHE_KEY, _collect_review_status_options),
    }


def list_gwflow_jobs(
    user,
    *,
    search="",
    library="",
    review_status="",
    time_range="all",
    page=1,
    page_size=20,
    offset=None,
    include_pruned=False,
):
    """
    Mirror of list_public_jobs for the gwflow index. Returns the same result
    dict shape as list_public_jobs (jobs dict, records, has_next, total, page,
    page_size).
    """
    if offset is None:
        offset = (page - 1) * page_size
    else:
        page = (offset // page_size) + 1 if page_size else 1

    empty_result = {
        "jobs": {},
        "records": [],
        "has_next": False,
        "total": 0,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }

    if len(search) > 256:
        logger.warning("Rejected overlong GWFlow search expression")
        empty_result["state"] = "invalid"
        return empty_result

    try:
        es = get_es_client()
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        empty_result["state"] = "down"
        return empty_result

    # Intentional advanced syntax stays in a query_string must-clause; all
    # structured constraints (library, review status, time, visibility, pruning)
    # are encoded as DSL filter values so user input never reaches the query
    # parser as syntax. Complexity controls: expressions are capped at 256
    # chars and leading-wildcard / wildcard-analysis expansion is disabled.
    # Full Lucene query_string syntax (fielded, Boolean, fuzzy, regex) is an
    # intentional Issue #51 feature; residual parser cost is bounded by the
    # above controls and by Elasticsearch request timeouts / monitoring.
    # Unfielded queries rely on index.query.default_field (the bounded
    # _gwcloud.* set) rather than expanding across the dynamic metadata.*
    # tree; fielded expert queries to arbitrary known metadata.* paths remain
    # available.
    must = (
        [
            {
                "query_string": {
                    "query": search,
                    "allow_leading_wildcard": False,
                    "analyze_wildcard": False,
                }
            }
        ]
        if search
        else [{"match_all": {}}]
    )
    filters = []
    if library:
        filters.append({"term": {"_gwcloud.libraries": library}})
    if review_status:
        filters.append({"term": {"_gwcloud.reviewStatuses": review_status}})
    if time_range != "all":
        now = timezone.now()
        then = now - _time_range_to_timedelta(time_range)
        filters.append({"range": {"_gwcloud.lastUpdatedTime": {"gte": then.isoformat(), "lte": now.isoformat()}}})
    if not is_ligo_user(user):
        filters.append(_GWCLOUD_LIGO_ONLY_FILTER)
    if not include_pruned:
        filters.append(_GWCLOUD_PRUNED_FILTER)

    query = {"bool": {"must": must, "filter": filters}}

    try:
        results = es.search(
            index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
            query=query,
            size=page_size + 1,
            from_=offset,
            sort=[{"_gwcloud.lastUpdatedTime": {"order": "desc", "missing": "_last"}}],
            track_total_hits=True,
            request_timeout=10,
        )
    except elasticsearch.NotFoundError:
        logger.exception(
            "Elasticsearch gwflow index missing or not found: %s",
            settings.ELASTIC_SEARCH_GWFLOW_INDEX,
        )
        empty_result["state"] = "down"
        return empty_result
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        empty_result["state"] = "down"
        return empty_result
    except elasticsearch.exceptions.BadRequestError:
        logger.exception("Elasticsearch rejected the gwflow list query")
        empty_result["state"] = "invalid"
        return empty_result

    if not results or "hits" not in results:
        return empty_result
    total = _extract_es_total(results)
    if not results["hits"]["hits"]:
        empty_result["total"] = total
        return empty_result

    records = results["hits"]["hits"]
    numeric_records = _numeric_es_records(records)
    # Continuation follows the exact ES total (same population as `total`), not
    # the numeric-only records, so non-numeric IDs cannot hide the next page.
    has_next = offset + page_size < total

    hit_ids = [record["_id"] for record in numeric_records]
    qs_before = GWFlowJob.objects.filter(id__in=hit_ids).select_related("event_id", "user").prefetch_related("files")

    qs_after = qs_before
    if not is_ligo_user(user):
        qs_after = qs_after.filter(ligo_only=False)

    if not include_pruned:
        qs_after = qs_after.filter(is_pruned=False)

    jobs = {job.id: job for job in qs_after}

    # Reconcile ES hits against the DB: preserve authorised rows and surface
    # stale (missing DB row) vs restricted (policy-filtered) records separately
    # instead of blanking the whole page on any single mismatch.
    authorized_ids = set(jobs)
    es_ids = set(hit_ids)
    if authorized_ids != es_ids:
        user_id = user.id if user and user.is_authenticated else 0
        db_ids = set(qs_before.values_list("id", flat=True))
        stale_ids = es_ids - db_ids
        restricted_ids = es_ids - authorized_ids - stale_ids
        if stale_ids:
            logger.warning(
                "GWFlow ES index has %d stale record(s) with no DB row (user %s)",
                len(stale_ids),
                user_id,
            )
        if restricted_ids:
            logger.warning(
                "User %s query excluded %d restricted or pruned GWFlowJob record(s)",
                user_id,
                len(restricted_ids),
            )
        # Preserve the global ES total and continuation state. The authoritative
        # `jobs` mapping already omits stale or restricted rows from rendering,
        # so index drift must not collapse pagination to a page-local count
        # (which would make valid later pages unreachable).

    return {
        "jobs": jobs,
        "records": numeric_records,
        "has_next": has_next,
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }
