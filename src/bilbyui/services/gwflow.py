import logging

import elasticsearch
from django.conf import settings
from django.utils import timezone

from bilbyui.models import GWFlowJob
from bilbyui.services.jobs import _time_range_to_timedelta
from bilbyui.utils.misc import is_ligo_user

logger = logging.getLogger(__name__)


def list_gwflow_jobs(
    user,
    *,
    search="",
    time_range="all",
    page=1,
    page_size=20,
    offset=None,
    include_pruned=False,
):
    """
    Mirror of list_public_jobs for the gwflow index. Returns the same result
    dict shape as list_public_jobs (jobs dict, records, has_next, page, page_size).
    """
    if offset is None:
        offset = (page - 1) * page_size
    else:
        page = (offset // page_size) + 1 if page_size else 1

    empty_result = {
        "jobs": {},
        "records": [],
        "has_next": False,
        "page": page,
        "page_size": page_size,
    }

    q = search or "*"

    if "_private_info_" in q:
        user_id = user.id if user and user.is_authenticated else 0
        logger.warning("User %s attempted to search private info in gwflow index", user_id)
        return empty_result

    try:
        es = elasticsearch.Elasticsearch(
            hosts=[settings.ELASTIC_SEARCH_HOST],
            api_key=settings.ELASTIC_SEARCH_API_KEY,
            verify_certs=False,
        )
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
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
        )
    except elasticsearch.NotFoundError:
        logger.exception(
            "Elasticsearch gwflow index missing or not found: %s",
            settings.ELASTIC_SEARCH_GWFLOW_INDEX,
        )
        return empty_result
    except elasticsearch.exceptions.ConnectionError:
        logger.exception("Failed to connect to Elasticsearch")
        return empty_result

    if not results or "hits" not in results or not results["hits"]["hits"]:
        return empty_result

    records = results["hits"]["hits"]
    has_next = len(records) > page_size
    records_to_return = records[:page_size]

    hit_ids = [record["_id"] for record in records_to_return]
    qs_before = GWFlowJob.objects.filter(id__in=hit_ids).select_related("event_id", "user")

    qs_after = qs_before
    if not is_ligo_user(user):
        qs_after = qs_after.filter(ligo_only=False)

    if not include_pruned:
        qs_after = qs_after.filter(is_pruned=False)

    if qs_before.count() != qs_after.count():
        user_id = user.id if user and user.is_authenticated else 0
        logger.warning(
            "User %s query returned unauthorized or pruned GWFlowJob records during reconciliation",
            user_id,
        )
        return empty_result

    jobs = {job.id: job for job in qs_after}

    return {
        "jobs": jobs,
        "records": records_to_return,
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
    }
