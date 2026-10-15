import logging
import math
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


def portal_get(path: str, *, cache_key: str):
    """GET {CBCFLOW_PORTAL_URL}{path} with header
    Authorization: <CBCFLOW_PORTAL_TOKEN> (raw UUID, no prefix).
    Serve a cached copy as (data, "stale") when present within TTL, avoiding a
    portal round-trip. Otherwise GET the portal; on 200 store response.json()
    in django cache under cache_key (TTL) and return (data, "live"). On any
    requests exception / non-200 with no cache: (None, "down").
    If CBCFLOW_PORTAL_URL/TOKEN are None: (None, "down") with a logged warning."""
    url = settings.CBCFLOW_PORTAL_URL
    token = settings.CBCFLOW_PORTAL_TOKEN
    if not url or not token:
        logger.warning("CBCFLOW_PORTAL_URL/TOKEN not configured; portal unavailable")
        return None, "down"
    cache = caches["default"]
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, "stale"
    try:
        resp = requests.get(
            f"{url}{path}",
            headers={"Authorization": token},
            timeout=PORTAL_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data, "live"
        logger.warning("Portal request failed for %s: unexpected status %s", path, resp.status_code)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Portal request failed for %s: %s", path, exc)
    return None, "down"


def get_superevent(sname):
    return portal_get(f"/api/v1/superevents/{sname}/", cache_key=f"gwflow:se:{sname}")


def get_versions(sname):
    return portal_get(f"/api/v1/superevents/{sname}/versions/", cache_key=f"gwflow:versions:{sname}")


def get_version(sname, sha):
    return portal_get(f"/api/v1/superevents/{sname}/versions/{sha}/", cache_key=f"gwflow:version:{sname}:{sha}")


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

    timestamp = normalise_current_history_timestamp(summary.get("commit_timestamp"))
    if timestamp is None:
        logger.warning(
            "Current-version summary for %s (%s) has no usable commit_timestamp",
            sname,
            commit_sha,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="current summary has no usable commit_timestamp",
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
