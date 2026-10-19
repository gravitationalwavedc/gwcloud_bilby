import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import caches

from bilbyui.models import EventID
from bilbyui.utils.embargo import _gwflow_trigger_time_from_metadata
from bilbyui.utils.gwflow_es import _parse_portal_bool
from bilbyui.utils.gwflow_version import normalise_current_history_timestamp

logger = logging.getLogger(__name__)

PORTAL_TIMEOUT = 10  # seconds
CACHE_TTL = 60 * 10  # 10 minutes
PORTAL_MAX_ATTEMPTS = 3
PORTAL_INITIAL_BACKOFF = 1.0


DETAIL_REQUIRED_FIELDS = (
    "sname",
    "libraries",
    "version_number",
    "record_timestamp",
    "commit_sha",
    "is_current",
    "analyses",
    "detector_configurations",
    "gracedb_events",
    "catalog_connections",
)
DETAIL_COLLECTION_FIELDS = (
    "analyses",
    "detector_configurations",
    "gracedb_events",
    "catalog_connections",
)


def _is_canonical_detail(data):
    return (
        isinstance(data, dict)
        and all(field in data for field in DETAIL_REQUIRED_FIELDS)
        and all(isinstance(data[field], list) for field in DETAIL_COLLECTION_FIELDS)
    )


DIFF_REQUIRED_FIELDS = (
    "sname",
    "baseline_version",
    "selected_version",
    "baseline_timestamp",
    "selected_timestamp",
    "changes",
)


def _is_canonical_diff(data):
    return (
        isinstance(data, dict)
        and all(field in data for field in DIFF_REQUIRED_FIELDS)
        and isinstance(data["sname"], str)
        and not isinstance(data["baseline_version"], bool)
        and isinstance(data["baseline_version"], int)
        and not isinstance(data["selected_version"], bool)
        and isinstance(data["selected_version"], int)
        and isinstance(data["baseline_timestamp"], str)
        and isinstance(data["selected_timestamp"], str)
        and isinstance(data["changes"], list)
    )


def portal_get(path: str, *, cache_key: str, validator=None, sname=None):
    """Fetch and cache a portal response.

    The return state is ``"live"``, ``"stale"``, ``"down"``, or
    ``"malformed"``. Cached values retain the established stale semantics but
    are still checked by an endpoint-specific validator when one is supplied.
    """
    url = settings.CBCFLOW_PORTAL_URL
    token = settings.CBCFLOW_PORTAL_TOKEN
    if not url or not token:
        logger.warning("CBCFLOW_PORTAL_URL/TOKEN not configured; portal unavailable")
        return None, "down"

    cache = caches["default"]
    cached = cache.get(cache_key)
    if cached is not None:
        if validator is not None and not validator(cached):
            logger.error(
                "Malformed portal response for %s (sname=%s)",
                path,
                sname,
            )
            return None, "malformed"
        return cached, "stale"

    backoff = PORTAL_INITIAL_BACKOFF
    response_data = None
    request_failed = False
    for attempt in range(1, PORTAL_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                f"{url}{path}",
                headers={"Authorization": token},
                timeout=PORTAL_TIMEOUT,
            )
            if resp.status_code < 500:
                if resp.status_code != 200:
                    logger.warning(
                        "Portal request failed for %s: unexpected status %s",
                        path,
                        resp.status_code,
                    )
                    request_failed = True
                    break
                try:
                    response_data = resp.json()
                except ValueError as exc:
                    logger.error(
                        "Malformed portal response for %s (sname=%s): %s",
                        path,
                        sname,
                        exc,
                    )
                    return None, "malformed"
                break
            logger.warning(
                "Portal request attempt %s failed for %s with status %s",
                attempt,
                path,
                resp.status_code,
            )
            request_failed = True
        except requests.RequestException as exc:
            logger.warning(
                "Portal request attempt %s failed for %s: %s",
                attempt,
                path,
                exc,
            )
            request_failed = True

        if attempt < PORTAL_MAX_ATTEMPTS:
            time.sleep(backoff)
            backoff *= 2.0

    if request_failed and response_data is None:
        cached = cache.get(cache_key)
        if cached is not None:
            if validator is not None and not validator(cached):
                logger.error("Malformed portal response for %s (sname=%s)", path, sname)
                return None, "malformed"
            return cached, "stale"
        return None, "down"

    if validator is not None and not validator(response_data):
        logger.error("Malformed portal response for %s (sname=%s)", path, sname)
        return None, "malformed"

    cache.set(cache_key, response_data, CACHE_TTL)
    return response_data, "live"


def get_superevent(sname):
    return portal_get(
        f"/api/v1/superevents/{sname}/",
        cache_key=f"gwflow:se:{sname}",
        validator=_is_canonical_detail,
        sname=sname,
    )


def get_versions(sname):
    return portal_get(
        f"/api/v1/superevents/{sname}/versions/",
        cache_key=f"gwflow:versions:{sname}",
        sname=sname,
    )


def get_version(sname, sha):
    return portal_get(
        f"/api/v1/superevents/{sname}/versions/{sha}/",
        cache_key=f"gwflow:version:{sname}:{sha}",
        validator=_is_canonical_detail,
        sname=sname,
    )


def get_diff(sname, baseline, selected):
    return portal_get(
        f"/api/v1/superevents/{sname}/diff/?baseline={baseline}&selected={selected}",
        cache_key=f"gwflow:diff:{sname}:{baseline}:{selected}",
        validator=_is_canonical_diff,
        sname=sname,
    )


@dataclass(frozen=True)
class GWFlowCurrentVersion:
    """Coherent result of resolving one portal current-version summary."""

    available: bool
    trigger_time: float | None = None
    current_history_id: str | None = None
    current_history_timestamp: datetime | None = None
    versions_state: str | None = None
    detail_state: str | None = None
    reason: str | None = None


def resolve_current_version(sname):
    """Resolve authoritative trigger and history fields for ``sname``.

    The selected summary, exact detail, trigger time, history identifier, and
    history timestamp form one unit. This helper performs no database writes
    and never falls back to EventID GPS.
    """
    try:
        versions, versions_state = get_versions(sname)
    except Exception as exc:
        logger.warning("Current-version summary fetch failed for %s: %s", sname, exc)
        return GWFlowCurrentVersion(
            available=False,
            reason="versions fetch failed",
        )

    if not isinstance(versions, list):
        logger.warning(
            "Current-version summaries unavailable for %s: expected list, got %s",
            sname,
            type(versions).__name__,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="versions response is not a list",
        )

    current = [
        summary for summary in versions if isinstance(summary, dict) and _parse_portal_bool(summary.get("is_current"))
    ]
    if len(current) != 1:
        logger.warning(
            "Current-version summaries unavailable for %s: found %d current summaries",
            sname,
            len(current),
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason=f"expected one current summary, found {len(current)}",
        )

    summary = current[0]
    commit_sha = summary.get("commit_sha")
    if not isinstance(commit_sha, str) or not commit_sha.strip():
        logger.warning("Current-version summary for %s has no usable commit_sha", sname)
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="current summary has no usable commit_sha",
        )
    commit_sha = commit_sha.strip()

    timestamp = normalise_current_history_timestamp(summary.get("record_timestamp"))
    if timestamp is None:
        logger.warning(
            "Current-version summary for %s (%s) has no usable record_timestamp",
            sname,
            commit_sha,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="current summary has no usable record_timestamp",
        )

    try:
        detail, detail_state = get_version(sname, commit_sha)
    except Exception as exc:
        logger.warning(
            "Current-version detail fetch failed for %s (%s): %s",
            sname,
            commit_sha,
            exc,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="detail fetch failed",
        )

    if not isinstance(detail, dict):
        logger.warning(
            "Current-version detail unavailable for %s (%s): expected dict, got %s",
            sname,
            commit_sha,
            type(detail).__name__,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            detail_state=detail_state,
            reason="detail response is not a dict",
        )

    raw_payload = detail.get("raw_payload")
    if not isinstance(raw_payload, dict):
        logger.warning(
            "Current-version detail unavailable for %s (%s): raw_payload is not a dict",
            sname,
            commit_sha,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            detail_state=detail_state,
            reason="detail raw_payload is not a dict",
        )

    trigger_time = _gwflow_trigger_time_from_metadata(raw_payload)
    if isinstance(trigger_time, bool) or not isinstance(trigger_time, (int, float)) or not math.isfinite(trigger_time):
        logger.warning(
            "Current-version detail unavailable for %s (%s): no usable finite trigger time",
            sname,
            commit_sha,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            detail_state=detail_state,
            reason="detail has no usable finite trigger time",
        )

    return GWFlowCurrentVersion(
        available=True,
        trigger_time=float(trigger_time),
        current_history_id=commit_sha,
        current_history_timestamp=timestamp,
        versions_state=versions_state,
        detail_state=detail_state,
    )


def resolve_event_id_for_superevent(sname):
    """Return the unique EventID owned by ``sname``, otherwise ``None``."""
    matches = list(EventID.objects.filter(trigger_id=sname).order_by("pk")[:2])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "Ambiguous EventID ownership for superevent %s; matching row ids include %s",
            sname,
            [event.pk for event in matches],
        )
    return None
