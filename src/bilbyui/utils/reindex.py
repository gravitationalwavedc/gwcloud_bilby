"""Bounded Elasticsearch reindexing and independent trigger-time verification."""

import logging
import math
import time
from collections.abc import Iterable
from typing import NamedTuple

import elasticsearch
import numpy as np
from django.conf import settings
from elasticsearch import helpers

from bilbyui.models import BilbyJob, GWFlowJob, build_bilby_es_doc
from bilbyui.utils.gwflow_es import build_gwflow_es_doc, get_es_client
from bilbyui.utils.gwflow_portal import get_version
from bilbyui.utils.search_trigger_time import max_finite_time

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 200
_RETRYABLE_STATUSES = {429, 502, 503, 504}


class ReindexCounts(NamedTuple):
    scanned: int
    succeeded: int
    failed: int


class ParityReport(NamedTuple):
    checked: int
    failures: int
    details: list


class ReindexError(RuntimeError):
    """Raised when one or more requested records cannot be reindexed."""


def _pages(values: list[int], size: int = _CHUNK_SIZE):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _item_details(item):
    if not isinstance(item, dict) or not item:
        return None, None, "malformed bulk item response"
    result = next(iter(item.values()))
    if not isinstance(result, dict):
        return None, None, "malformed bulk item response"
    stable_id = result.get("_id")
    status = result.get("status")
    error = result.get("error")
    if isinstance(error, dict):
        reason = error.get("reason") or error.get("type") or "bulk item failure"
    elif error:
        reason = str(error)
    else:
        reason = f"bulk item status {status}"
    return stable_id, status, reason


def _bulk_actions(es, actions, kind):
    pending = {str(action["_id"]): action for action in actions}
    succeeded = 0
    permanent = set()

    for attempt in range(3):
        if not pending:
            break
        if attempt:
            time.sleep(0.5 if attempt == 1 else 1)

        current = dict(pending)
        try:
            _, errors = helpers.bulk(
                es,
                list(current.values()),
                raise_on_error=False,
                raise_on_exception=False,
                stats_only=False,
            )
        except (elasticsearch.TransportError, elasticsearch.ConnectionError) as exc:
            logger.warning(
                "reindex operation=bulk kind=%s stable_id=batch reason=%s",
                kind,
                type(exc).__name__,
            )
            continue

        failed_ids = set()
        malformed_response = False
        for item in errors or []:
            stable_id, status, reason = _item_details(item)
            key = str(stable_id) if stable_id is not None else None
            if key not in current:
                malformed_response = True
                logger.error(
                    "reindex operation=bulk kind=%s stable_id=%s reason=%s",
                    kind,
                    key or "unknown",
                    reason,
                )
                continue
            failed_ids.add(key)
            if status in _RETRYABLE_STATUSES:
                logger.warning(
                    "reindex operation=retry kind=%s stable_id=%s reason=status %s",
                    kind,
                    key,
                    status,
                )
            else:
                permanent.add(key)
                pending.pop(key, None)
                logger.error(
                    "reindex operation=bulk kind=%s stable_id=%s reason=%s",
                    kind,
                    key,
                    reason,
                )

        if malformed_response:
            for key in current:
                permanent.add(key)
                pending.pop(key, None)
            break

        successful_ids = set(current) - failed_ids
        for key in successful_ids:
            pending.pop(key, None)
        succeeded += len(successful_ids)

        for key in failed_ids:
            if key not in permanent:
                pending[key] = current[key]

    exhausted = set(pending)
    for key in exhausted:
        logger.error(
            "reindex operation=bulk kind=%s stable_id=%s reason=retry attempts exhausted",
            kind,
            key,
        )
    return succeeded, len(permanent | exhausted)


def _build_actions(requested_ids, kind):
    if kind == "bilby":
        rows = BilbyJob.objects.filter(id__in=requested_ids).select_related(
            "event_id",
            "gwflow_job__event_id",
        )
        index = settings.ELASTIC_SEARCH_INDEX
    else:
        rows = GWFlowJob.objects.filter(id__in=requested_ids).select_related("event_id")
        index = settings.ELASTIC_SEARCH_GWFLOW_INDEX

    rows_by_id = {row.id: row for row in rows}
    actions = []
    failed = 0

    for stable_id in requested_ids:
        job = rows_by_id.get(stable_id)
        if job is None:
            failed += 1
            logger.error(
                "reindex operation=build kind=%s stable_id=%s reason=source row missing",
                kind,
                stable_id,
            )
            continue

        try:
            if kind == "bilby":
                document = build_bilby_es_doc(job)
                if document is None:
                    raise ValueError("canonical builder returned no document")
            else:
                metadata, state = get_version(job.sname, job.current_history_id)
                if state == "down" or metadata is None:
                    raise ValueError("portal metadata unavailable")
                document = build_gwflow_es_doc(job, metadata)
        except Exception as exc:
            failed += 1
            logger.error(
                "reindex operation=build kind=%s stable_id=%s reason=%s",
                kind,
                stable_id,
                str(exc),
            )
            continue

        actions.append(
            {
                "_op_type": "index",
                "_index": index,
                "_id": job.id,
                "_source": document,
            }
        )

    return actions, failed


def reindex_jobs(ids: Iterable[int], kind: str) -> ReindexCounts:
    """Rebuild requested jobs in bounded, stable-ID bulk writes."""
    if kind not in {"bilby", "gwflow"}:
        raise ValueError("kind must be 'bilby' or 'gwflow'")

    # This mirrors the guards inside elastic_search_update / gwflow_elastic_search_update.
    if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
        return ReindexCounts(0, 0, 0)

    requested = sorted(set(ids))
    if not requested:
        return ReindexCounts(0, 0, 0)

    es = get_es_client()
    scanned = 0
    succeeded = 0
    failed = 0

    for requested_page in _pages(requested):
        actions, build_failed = _build_actions(requested_page, kind)
        page_succeeded, bulk_failed = _bulk_actions(es, actions, kind)
        scanned += len(requested_page)
        succeeded += page_succeeded
        failed += build_failed + bulk_failed
        if build_failed or bulk_failed:
            if scanned != succeeded + failed:
                raise AssertionError("inconsistent reindex counts")
            raise ReindexError(
                f"reindex operation failed kind={kind} scanned={scanned} succeeded={succeeded} failed={failed}"
            )

    counts = ReindexCounts(scanned, succeeded, failed)
    if counts.scanned != counts.succeeded + counts.failed:
        raise AssertionError("inconsistent reindex counts")
    return counts


def _accumulate(total, counts):
    return ReindexCounts(
        total.scanned + counts.scanned,
        total.succeeded + counts.succeeded,
        total.failed + counts.failed,
    )


def _reindex_id_queryset(queryset, kind, total):
    buffer = []
    for stable_id in queryset.iterator(chunk_size=_CHUNK_SIZE):
        buffer.append(stable_id)
        if len(buffer) == _CHUNK_SIZE:
            total = _accumulate(total, reindex_jobs(buffer, kind))
            buffer = []
    if buffer:
        total = _accumulate(total, reindex_jobs(buffer, kind))
    return total


def reindex_affected_event(event_id) -> ReindexCounts:
    """Reindex all Bilby and GWFlow documents affected by an EventID."""
    direct = BilbyJob.objects.filter(event_id_id=event_id).order_by().values_list("id", flat=True)
    children = BilbyJob.objects.filter(gwflow_job__event_id_id=event_id).order_by().values_list("id", flat=True)
    bilby_ids = direct.union(children).order_by("id")
    gwflow_ids = GWFlowJob.objects.filter(event_id_id=event_id).order_by("id").values_list("id", flat=True)

    total = ReindexCounts(0, 0, 0)
    total = _reindex_id_queryset(bilby_ids, "bilby", total)
    return _reindex_id_queryset(gwflow_ids, "gwflow", total)


def _finite_numeric(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        numeric = float(value)
    except OverflowError:
        return None
    return numeric if math.isfinite(numeric) else None


def _expected_trigger_time(job, kind):
    if kind == "bilby":
        values = [
            job.trigger_time,
            job.event_id.gps_time if job.event_id else None,
            job.gwflow_job.trigger_time if job.gwflow_job else None,
            (job.gwflow_job.event_id.gps_time if job.gwflow_job and job.gwflow_job.event_id else None),
        ]
    else:
        values = [
            job.trigger_time,
            job.event_id.gps_time if job.event_id else None,
        ]
    return max_finite_time(values)


def _stored_trigger_time(source, kind):
    if not isinstance(source, dict):
        return False, None
    if kind == "bilby":
        return ("searchTriggerTime" in source), source.get("searchTriggerTime")
    envelope = source.get("_gwcloud")
    if not isinstance(envelope, dict):
        return False, None
    return ("searchTriggerTime" in envelope), envelope.get("searchTriggerTime")


def _collect_search_trigger_time_parity(kind: str, *, batch: int = _CHUNK_SIZE) -> ParityReport:
    """Independently compare raw model fields with stored Elasticsearch values."""
    if kind not in {"bilby", "gwflow"}:
        raise ValueError("kind must be 'bilby' or 'gwflow'")

    if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
        return ParityReport(0, 0, [])

    if kind == "bilby":
        queryset = BilbyJob.objects.select_related(
            "event_id",
            "gwflow_job__event_id",
        ).order_by("id")
        index = settings.ELASTIC_SEARCH_INDEX
    else:
        queryset = GWFlowJob.objects.select_related("event_id").order_by("id")
        index = settings.ELASTIC_SEARCH_GWFLOW_INDEX

    es = get_es_client()
    cursor = 0
    failures = 0
    checked = 0
    details = []

    while True:
        rows = list(queryset.filter(id__gt=cursor)[:batch])
        if not rows:
            break

        response = es.mget(index=index, ids=[row.id for row in rows])
        documents = {
            str(document.get("_id")): document for document in response.get("docs", []) if isinstance(document, dict)
        }

        for job in rows:
            checked += 1
            document = documents.get(str(job.id))
            reason = None
            if not document or not document.get("found", False):
                reason = "stored document missing"
            else:
                expected = _expected_trigger_time(job, kind)
                present, actual = _stored_trigger_time(document.get("_source"), kind)
                if expected is None:
                    if present:
                        reason = "field present without finite source value"
                elif not present:
                    reason = "field missing"
                else:
                    numeric = _finite_numeric(actual)
                    if numeric is None:
                        reason = "field is not finite numeric"
                    elif numeric != expected:
                        reason = "field value mismatch"

            if reason:
                failures += 1
                if len(details) < 100:
                    details.append((job.id, reason))
                logger.error(
                    "reindex operation=verify kind=%s stable_id=%s reason=%s",
                    kind,
                    job.id,
                    reason,
                )

        cursor = rows[-1].id

    logger.info(
        "reindex operation=verify kind=%s stable_id=all reason=checked %s failures %s",
        kind,
        checked,
        failures,
    )
    return ParityReport(checked, failures, details)


def verify_search_trigger_time(kind: str) -> None:
    """Independently compare raw model fields with stored Elasticsearch values."""
    report = _collect_search_trigger_time_parity(kind)
    if report.failures:
        raise ReindexError(f"verification failed kind={kind} checked={report.checked} failures={report.failures}")
