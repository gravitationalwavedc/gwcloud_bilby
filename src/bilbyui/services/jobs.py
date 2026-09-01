import logging
from datetime import timedelta

import elasticsearch
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.utils.embargo import embargo_filter, user_subject_to_embargo
from bilbyui.utils.gwflow_es import get_es_client
from bilbyui.utils.job_validation import validate_job_name
from bilbyui.utils.jobs.request_job_filter import request_job_filter

logger = logging.getLogger(__name__)


_TIME_RANGE_DELTAS = {
    "1d": timedelta(days=1),
    "1w": timedelta(days=7),
    "1m": timedelta(days=31),
    "1y": timedelta(days=365),
}


def _time_range_to_timedelta(time_range):
    try:
        return _TIME_RANGE_DELTAS[time_range]
    except KeyError:
        msg = f"Unexpected timeRange value {time_range}"
        raise ValueError(msg) from None


def _numeric_es_records(records):
    return [
        record
        for record in records
        if isinstance(record, dict) and (isinstance(record.get("_id"), int) or str(record.get("_id")).isdigit())
    ]


def _extract_es_total(results):
    """Return the total hit count from an ES response, guarding against a
    missing total block, a string-typed value, or the legacy integer shape.

    A lower-bound total (``relation != "eq"``, e.g. a capped 10000) is never
    presented as exact: the helper returns 0 so pagination does not truncate
    against a value that understates the real hit count. Callers that need an
    exact total issue the search with ``track_total_hits=True``.
    """
    try:
        total = results["hits"]["total"]
    except (KeyError, TypeError):
        return 0
    if isinstance(total, dict):
        if total.get("relation", "eq") != "eq":
            return 0
        total = total.get("value", 0)
    if isinstance(total, str):
        try:
            return int(total)
        except (TypeError, ValueError):
            return 0
    return total if isinstance(total, int) else 0


def _apply_time_range_filter(qs, time_range, field_name="last_updated"):
    if time_range == "all":
        return qs

    then = timezone.now() - _time_range_to_timedelta(time_range)

    return qs.filter(**{f"{field_name}__gte": then})


def _apply_search_filter(qs, search):
    if not search:
        return qs
    return qs.filter(Q(name__icontains=search) | Q(description__icontains=search))


def list_user_jobs(user, *, search="", time_range="all", page=1, page_size=20):
    # DB-backed (BilbyJob queryset) — no Elasticsearch/portal round-trip, so
    # there is no reachable infrastructure "down" state; the contract always
    # reports "ok" (a DB error surfaces as a 500, not a service-down result).
    qs = (
        BilbyJob.user_bilby_job_filter(BilbyJob.objects.all(), user)
        .select_related("event_id")
        .prefetch_related("labels")
        .order_by("-last_updated")
    )
    qs = _apply_search_filter(qs, search)
    qs = _apply_time_range_filter(qs, time_range)

    total = qs.count()

    offset = (page - 1) * page_size
    jobs_slice = list(qs[offset : offset + page_size + 1])
    has_next = len(jobs_slice) > page_size

    return {
        "jobs": jobs_slice[:page_size],
        "has_next": has_next,
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }


def _fetch_job_controller_jobs(jobs, user_id):
    job_controller_ids = {job.job_controller_id: job.id for job in jobs if job.job_controller_id}
    job_controller_jobs = {}
    if job_controller_ids:
        status, job_controller_result = request_job_filter(user_id, ids=job_controller_ids.keys())
        if status == "OK":
            job_controller_jobs = {
                job_controller_ids[job["id"]]: job
                for job in job_controller_result
                if isinstance(job, dict) and "id" in job and job["id"] in job_controller_ids
            }
    return job_controller_jobs


def list_public_jobs(user, *, search="", time_range="all", page=1, page_size=20, offset=None):
    if offset is None:
        offset = (page - 1) * page_size
    else:
        page = (offset // page_size) + 1 if page_size else 1

    empty_result = {
        "jobs": {},
        "records": [],
        "job_controller_jobs": {},
        "has_next": False,
        "total": 0,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }

    try:
        es = get_es_client()
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        empty_result["state"] = "down"
        return empty_result

    q = search or "*"

    if "_private_info_" in q:
        user_id = user.id if user.is_authenticated else 0
        msg = f"User {user_id} attempted to search private info"
        logger.warning(msg)
        return empty_result

    if time_range != "all":
        now = timezone.now()
        then = now - _time_range_to_timedelta(time_range)

        q = f'({q}) AND job.creationTime:["{then.isoformat()}" TO "{now.isoformat()}"]'

    q = f"({q}) AND _private_info_.private:false"

    if user_subject_to_embargo(user):
        q = f"({q}) AND (params.trigger_time:<{settings.EMBARGO_START_TIME} OR ini.n_simulation:>0)"

    try:
        results = es.search(
            index=settings.ELASTIC_SEARCH_INDEX,
            q=q,
            size=page_size + 1,
            from_=offset,
            sort="job.lastUpdatedTime:desc",
            track_total_hits=True,
        )
    except elasticsearch.NotFoundError:
        # Missing index (common in fresh local setups) — show empty list, not 500.
        logger.exception(
            "Elasticsearch index missing or not found: %s",
            settings.ELASTIC_SEARCH_INDEX,
        )
        empty_result["state"] = "down"
        return empty_result
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        empty_result["state"] = "down"
        return empty_result
    except elasticsearch.exceptions.BadRequestError:
        logger.exception("Elasticsearch rejected the public jobs list query")
        empty_result["state"] = "down"
        return empty_result

    if not results or "hits" not in results:
        return empty_result
    total = _extract_es_total(results)
    if not results["hits"]["hits"]:
        empty_result["total"] = total
        return empty_result

    records = _numeric_es_records(results["hits"]["hits"])
    # Continuation follows the exact ES total (same population as `total`), not
    # the numeric-only records, so non-numeric IDs cannot hide the next page.
    has_next = offset + page_size < total

    qs_before = (
        BilbyJob.objects.filter(id__in=[record["_id"] for record in records])
        .select_related("event_id")
        .prefetch_related("labels")
    )
    qs_after = qs_before
    if user_subject_to_embargo(user):
        qs_after = embargo_filter(qs_before, user)

    qs_after = qs_after.filter(private=False)

    jobs = {job.id: job for job in qs_after}

    # Reconcile ES hits against the DB: preserve authorised rows and surface
    # stale (missing DB row) vs restricted (policy-filtered) records separately
    # instead of blanking the whole page on any single mismatch.
    authorized_ids = set(jobs)
    es_ids = {record["_id"] for record in records}
    if authorized_ids != es_ids:
        user_id = user.id if user.is_authenticated else 0
        db_ids = set(qs_before.values_list("id", flat=True))
        stale_ids = es_ids - db_ids
        restricted_ids = es_ids - authorized_ids - stale_ids
        if stale_ids:
            logger.warning(
                "Bilby ES index has %d stale record(s) with no DB row (user %s)",
                len(stale_ids),
                user_id,
            )
        if restricted_ids:
            logger.warning(
                "User %s query excluded %d embargoed or private BilbyJob record(s)",
                user_id,
                len(restricted_ids),
            )
            # Fail closed: the ES total may include restricted records, so never
            # expose it as an exact count. Show only the authorised page-local
            # count with no continuation (a page-local count must not be
            # presented as a complete global total).
            total = len(jobs)
            has_next = False

    job_controller_jobs = _fetch_job_controller_jobs(jobs.values(), user.id if user.is_authenticated else 0)

    return {
        "jobs": jobs,
        "records": records,
        "job_controller_jobs": job_controller_jobs,
        "has_next": has_next,
        "total": total,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }


def get_job(job_id, user):
    return BilbyJob.get_by_id(job_id, user)


def update_job(job_id, user, private=None, labels=None, event_id=None, name=None, description=None):
    bilby_job = BilbyJob.get_by_id(job_id, user)

    if user.id == bilby_job.user_id:
        if labels is not None:
            protected_labels = bilby_job.labels.filter(protected=True)
            bilby_job.labels.set(Label.filter_by_name(labels) | protected_labels)

        if event_id is not None:
            bilby_job.event_id = None if event_id == "" else EventID.get_by_event_id(event_id, user)

        if private is not None:
            bilby_job.private = private

        if name is not None:
            validate_job_name(name)
            bilby_job.name = name

        if description is not None:
            bilby_job.description = description

        bilby_job.save()

        return True, "Job saved!"

    if user.id in settings.PERMITTED_EVENT_CREATION_USER_IDS and event_id is not None:
        bilby_job.event_id = None if event_id == "" else EventID.get_by_event_id(event_id, user)

        bilby_job.save()

        return True, "Job saved"

    msg = "You must own the job to change it!"
    raise PermissionError(msg)
