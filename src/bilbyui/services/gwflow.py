import logging

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
FILTER_OPTIONS_TTL = 3600
REVIEW_STATUS_FALLBACK = ["reviewed", "unreviewed", "pending", "approved"]

_ES_TERM_SPECIAL_CHARS = set('\\"*?:()[]{}')


def _escape_es_term(value):
    """Escape a value for safe insertion into an ES query_string exact-term
    clause. Backslash-escapes quotes, wildcards, colons, brackets, braces and
    whitespace so user-supplied filter values cannot alter the query."""
    return "".join(f"\\{ch}" if ch in _ES_TERM_SPECIAL_CHARS or ch.isspace() else ch for ch in str(value))


def _collect_library_options():
    libraries = set()
    for item in GWFlowJob.objects.filter(ligo_only=False).values_list("libraries", flat=True).iterator(chunk_size=2000):
        if not item:
            continue
        if isinstance(item, str):
            libraries.add(item)
        elif isinstance(item, (list, tuple)):
            for lib in item:
                if lib:
                    libraries.add(str(lib))
        else:
            libraries.add(str(item))
    return sorted(libraries, key=str.casefold)


def _collect_review_status_options():
    es_errors = (elasticsearch.exceptions.TransportError, elasticsearch.exceptions.ApiError)
    try:
        es = get_es_client()
    except es_errors:
        logger.exception("Failed to connect to Elasticsearch for review status aggregation")
        return None

    try:
        results = es.search(
            index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
            q="isPruned:false AND ligoOnly:false",
            size=0,
            aggs={
                "review_statuses": {
                    "terms": {"field": "analyses.reviewStatus.keyword", "size": 50},
                }
            },
        )
    except es_errors:
        logger.exception("Failed to aggregate review statuses from Elasticsearch")
        return None

    buckets = results.get("aggregations", {}).get("review_statuses", {}).get("buckets", [])
    statuses = [bucket.get("key") for bucket in buckets if isinstance(bucket, dict) and bucket.get("key")]
    if not statuses:
        return None
    return statuses


def list_gwflow_filter_options():
    """Return the filter options for the GWFlow job list surface:
    DB-driven libraries and ES-aggregated review statuses, both cached.

    The options reflect publicly-visible data only (ligo_only=False jobs and
    ligoOnly:false documents) because the cache is global and shared by all
    users. LIGO users can still reach any value via the advanced-syntax input.
    """
    libraries = cache.get(LIBRARIES_CACHE_KEY)
    if libraries is None:
        libraries = _collect_library_options()
        cache.set(LIBRARIES_CACHE_KEY, libraries, FILTER_OPTIONS_TTL)

    review_statuses = cache.get(REVIEW_STATUSES_CACHE_KEY)
    if review_statuses is None:
        review_statuses = _collect_review_status_options()
        if review_statuses is None:
            # ES unavailable or no buckets — hardcoded fallback, not cached so
            # the next call retries ES once it is back.
            review_statuses = REVIEW_STATUS_FALLBACK
        else:
            cache.set(REVIEW_STATUSES_CACHE_KEY, review_statuses, FILTER_OPTIONS_TTL)

    return {"libraries": libraries, "review_statuses": review_statuses}


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

    q = search or "*"

    if library:
        q = f'({q}) AND libraries:"{_escape_es_term(library)}"'
    if review_status:
        q = f'({q}) AND analyses.reviewStatus:"{_escape_es_term(review_status)}"'

    if "_private_info_" in q:
        user_id = user.id if user and user.is_authenticated else 0
        logger.warning("User %s attempted to search private info in gwflow index", user_id)
        return empty_result

    try:
        es = get_es_client()
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        empty_result["state"] = "down"
        return empty_result

    if time_range != "all":
        now = timezone.now()
        then = now - _time_range_to_timedelta(time_range)
        q = f'({q}) AND lastUpdatedTime:["{then.isoformat()}" TO "{now.isoformat()}"]'

    if not is_ligo_user(user):
        q = f"({q}) AND ligoOnly:false"

    if not include_pruned:
        q = f"({q}) AND isPruned:false"

    try:
        results = es.search(
            index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
            q=q,
            size=page_size + 1,
            from_=offset,
            sort="lastUpdatedTime:desc",
            track_total_hits=True,
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
        empty_result["state"] = "down"
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

    return {
        "jobs": jobs,
        "records": numeric_records,
        "has_next": has_next,
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }
