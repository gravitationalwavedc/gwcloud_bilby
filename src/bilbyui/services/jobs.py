import logging
from datetime import timedelta

import elasticsearch
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.utils.embargo import embargo_filter, user_subject_to_embargo
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
    qs = (
        BilbyJob.user_bilby_job_filter(BilbyJob.objects.all(), user)
        .select_related("event_id")
        .prefetch_related("labels")
        .order_by("-last_updated")
    )
    qs = _apply_search_filter(qs, search)
    qs = _apply_time_range_filter(qs, time_range)

    offset = (page - 1) * page_size
    jobs_slice = list(qs[offset : offset + page_size + 1])
    has_next = len(jobs_slice) > page_size

    return {
        "jobs": jobs_slice[:page_size],
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
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
        "page": page,
        "page_size": page_size,
    }

    try:
        es = elasticsearch.Elasticsearch(
            hosts=[settings.ELASTIC_SEARCH_HOST],
            api_key=settings.ELASTIC_SEARCH_API_KEY,
            verify_certs=False,
        )
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
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
        )
    except elasticsearch.NotFoundError:
        # Missing index (common in fresh local setups) — show empty list, not 500.
        logger.exception(
            "Elasticsearch index missing or not found: %s",
            settings.ELASTIC_SEARCH_INDEX,
        )
        return empty_result
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        return empty_result

    if not results["hits"]["hits"]:
        return empty_result

    records = results["hits"]["hits"]
    records = [
        record
        for record in records
        if isinstance(record, dict) and (isinstance(record.get("_id"), int) or str(record.get("_id")).isdigit())
    ]
    has_next = len(records) > page_size

    qs_before = (
        BilbyJob.objects.filter(id__in=[record["_id"] for record in records])
        .select_related("event_id")
        .prefetch_related("labels")
    )
    qs_after = qs_before
    if user_subject_to_embargo(user):
        qs_after = embargo_filter(qs_before, user)

    qs_after = qs_after.filter(private=False)

    if qs_before.count() != qs_after.count():
        user_id = user.id if user.is_authenticated else 0
        msg = f"User {user_id} query violated embargo or included private job"
        logger.warning(msg)
        return empty_result

    jobs = {job.id: job for job in qs_after}

    job_controller_jobs = _fetch_job_controller_jobs(jobs.values(), user.id if user.is_authenticated else 0)

    return {
        "jobs": jobs,
        "records": records,
        "job_controller_jobs": job_controller_jobs,
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
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
