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


def _time_range_to_timedelta(time_range):
    if time_range == "1d":
        return timedelta(days=1)
    if time_range == "1w":
        return timedelta(days=7)
    if time_range == "1m":
        return timedelta(days=31)
    if time_range == "1y":
        return timedelta(days=365)
    raise Exception(f"Unexpected timeRange value {time_range}")


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
    except Exception as e:
        logger.error(f"Failed to connect to Elasticsearch: {e}", exc_info=True)
        return empty_result

    q = search or "*"

    if "_private_info_" in q:
        user_id = user.id if user.is_authenticated else 0
        logger.warning(f"User {user_id} attempted to search private info")
        return empty_result

    if time_range != "all":
        now = timezone.now()
        then = now - _time_range_to_timedelta(time_range)

        q = f'({q}) AND job.creationTime:["{then.isoformat()}" TO "{now.isoformat()}"]'

    q = f"({q}) AND _private_info_.private:false"

    if user_subject_to_embargo(user):
        q = f"({q}) AND (params.trigger_time:<{settings.EMBARGO_START_TIME} OR ini.n_simulation:>0)"

    results = es.search(
        index=settings.ELASTIC_SEARCH_INDEX,
        q=q,
        size=page_size + 1,
        from_=offset,
        sort="job.lastUpdatedTime:desc",
    )

    if not results["hits"]:
        return empty_result

    records = results["hits"]["hits"]
    has_next = len(records) > page_size

    qs_before = BilbyJob.objects.filter(id__in=[record["_id"] for record in records]).select_related("event_id")
    qs_after = qs_before
    if user_subject_to_embargo(user):
        qs_after = embargo_filter(qs_before, user)

    qs_after = qs_after.filter(private=False)

    if qs_before.count() != qs_after.count():
        user_id = user.id if user.is_authenticated else 0
        logger.warning(f"User {user_id} query violated embargo or included private job")
        return empty_result

    jobs = {
        job.id: job
        for job in BilbyJob.objects.filter(id__in=[record["_id"] for record in records]).select_related("event_id")
    }

    job_controller_ids = {job.job_controller_id: job.id for job in jobs.values() if job.job_controller_id}
    job_controller_jobs = {}
    if job_controller_ids:
        user_id = user.id if user.is_authenticated else 0
        job_controller_jobs = {
            job_controller_ids[job["id"]]: job for job in request_job_filter(user_id, ids=job_controller_ids.keys())[1]
        }

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
            bilby_job.event_id = None if event_id == "" else EventID.objects.get(event_id=event_id)

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
        bilby_job.event_id = None if event_id == "" else EventID.objects.get(event_id=event_id)

        bilby_job.save()

        return True, "Job saved"

    raise Exception("You must own the job to change it!")
