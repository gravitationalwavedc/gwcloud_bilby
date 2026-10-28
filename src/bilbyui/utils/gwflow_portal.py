import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit

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
        and all(
            isinstance(data[field], str) and bool(data[field].strip())
            for field in ("sname", "record_timestamp", "commit_sha")
        )
        and isinstance(data["libraries"], list)
        and isinstance(data["version_number"], int)
        and not isinstance(data["version_number"], bool)
        # Portal booleans may deliberately arrive as parseable strings.
        and isinstance(data["is_current"], (bool, str))
        and all(isinstance(data[field], list) for field in DETAIL_COLLECTION_FIELDS)
        and ("raw_payload" not in data or data["raw_payload"] is None or isinstance(data["raw_payload"], dict))
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


def _request_portal_json(url, *, path, sname=None):
    """Request one portal JSON document using the shared bounded retry policy."""
    token = settings.CBCFLOW_PORTAL_TOKEN
    backoff = PORTAL_INITIAL_BACKOFF

    for attempt in range(1, PORTAL_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
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
                    return None, "failed"
                try:
                    return resp.json(), "live"
                except (ValueError, RecursionError) as exc:
                    logger.error(
                        "Malformed portal response for %s (sname=%s): %s",
                        path,
                        sname,
                        exc,
                    )
                    return None, "malformed"

            logger.warning(
                "Portal request attempt %s failed for %s with status %s",
                attempt,
                path,
                resp.status_code,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Portal request attempt %s failed for %s: %s",
                attempt,
                path,
                exc,
            )

        if attempt < PORTAL_MAX_ATTEMPTS:
            time.sleep(backoff)
            backoff *= 2.0

    return None, "down"


def _validated_cached(cache, cache_key, *, path, validator=None, sname=None):
    cached = cache.get(cache_key)
    if cached is None:
        return None, None
    if validator is not None and not validator(cached):
        logger.error("Malformed portal response for %s (sname=%s)", path, sname)
        return None, "malformed"
    return cached, "stale"


def portal_get(path: str, *, cache_key: str, validator=None, sname=None):
    """Fetch and cache a portal response.

    The return state is ``"live"``, ``"stale"``, ``"down"``, ``"failed"``,
    or ``"malformed"``. Cached values retain the established stale semantics
    but are still checked by an endpoint-specific validator when supplied.
    """
    url = settings.CBCFLOW_PORTAL_URL
    token = settings.CBCFLOW_PORTAL_TOKEN
    if not url or not token:
        logger.warning("CBCFLOW_PORTAL_URL/TOKEN not configured; portal unavailable")
        return None, "down"

    cache = caches["default"]
    cached, cached_state = _validated_cached(
        cache,
        cache_key,
        path=path,
        validator=validator,
        sname=sname,
    )
    if cached_state is not None:
        return cached, cached_state

    response_data, state = _request_portal_json(
        f"{url}{path}",
        path=path,
        sname=sname,
    )
    if state in ("down", "failed"):
        cached, cached_state = _validated_cached(
            cache,
            cache_key,
            path=path,
            validator=validator,
            sname=sname,
        )
        if cached_state is not None:
            return cached, cached_state
        return None, state
    if state != "live":
        return None, state

    if validator is not None and not validator(response_data):
        logger.error("Malformed portal response for %s (sname=%s)", path, sname)
        return None, "malformed"

    cache.set(cache_key, response_data, CACHE_TTL)
    return response_data, "live"


VERSION_ENVELOPE_FIELDS = {"count", "next", "previous", "results"}


def _is_canonical_versions_envelope(data):
    return (
        isinstance(data, dict)
        and set(data) == VERSION_ENVELOPE_FIELDS
        and isinstance(data["count"], int)
        and not isinstance(data["count"], bool)
        and (data["next"] is None or isinstance(data["next"], str))
        and (data["previous"] is None or isinstance(data["previous"], str))
        and isinstance(data["results"], list)
    )


def _same_portal_origin(url):
    portal = urlsplit(settings.CBCFLOW_PORTAL_URL)
    candidate = urlsplit(url)
    return (candidate.scheme, candidate.netloc) == (portal.scheme, portal.netloc)


def _get_versions_collection(path, *, cache_key, sname):
    portal_url = settings.CBCFLOW_PORTAL_URL
    token = settings.CBCFLOW_PORTAL_TOKEN
    if not portal_url or not token:
        logger.warning("CBCFLOW_PORTAL_URL/TOKEN not configured; portal unavailable")
        return None, "down"

    cache = caches["default"]
    cached, cached_state = _validated_cached(
        cache,
        cache_key,
        path=path,
        validator=lambda value: isinstance(value, list),
        sname=sname,
    )
    if cached_state is not None:
        return cached, cached_state

    page_url = f"{portal_url.rstrip('/')}{path}?page=1"
    seen_urls = set()
    flattened = []

    while page_url is not None:
        if not _same_portal_origin(page_url) or page_url in seen_urls:
            logger.error(
                "Malformed portal pagination for %s (sname=%s): unsafe or cyclic next URL",
                path,
                sname,
            )
            return None, "malformed"
        seen_urls.add(page_url)

        envelope, state = _request_portal_json(page_url, path=path, sname=sname)
        if state in ("down", "failed"):
            cached, cached_state = _validated_cached(
                cache,
                cache_key,
                path=path,
                validator=lambda value: isinstance(value, list),
                sname=sname,
            )
            if cached_state is not None:
                return cached, cached_state
            return None, state
        if state != "live":
            return None, state
        if not _is_canonical_versions_envelope(envelope):
            logger.error("Malformed portal response for %s (sname=%s)", path, sname)
            return None, "malformed"

        flattened.extend(envelope["results"])
        next_url = envelope["next"]
        page_url = urljoin(page_url, next_url) if next_url is not None else None
        if page_url is not None and not _same_portal_origin(page_url):
            logger.error(
                "Malformed portal pagination for %s (sname=%s): cross-origin next URL",
                path,
                sname,
            )
            return None, "malformed"

    cache.set(cache_key, flattened, CACHE_TTL)
    return flattened, "live"


def get_superevent(sname):
    return portal_get(
        f"/api/v1/superevents/{sname}/",
        cache_key=f"gwflow:se:{sname}",
        validator=_is_canonical_detail,
        sname=sname,
    )


def get_versions(sname):
    return _get_versions_collection(
        f"/api/v1/superevents/{sname}/versions/",
        cache_key=f"gwflow:versions:{sname}",
        sname=sname,
    )


def get_version(sname, version_number):
    """Fetch one version using its canonical integer transport key."""
    if isinstance(version_number, bool) or not isinstance(version_number, int):
        return None, "failed"

    return portal_get(
        f"/api/v1/superevents/{sname}/versions/{version_number}/",
        cache_key=f"gwflow:version:{sname}:{version_number}",
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
    current_version_number: int | None = None
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
    version_number = summary.get("version_number")
    if not isinstance(version_number, int) or isinstance(version_number, bool):
        logger.warning("Current-version summary for %s has no usable version_number", sname)
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="current summary has no usable version_number",
        )

    timestamp = normalise_current_history_timestamp(summary.get("record_timestamp"))
    if timestamp is None:
        logger.warning(
            "Current-version summary for %s (v%s) has no usable record_timestamp",
            sname,
            version_number,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="current summary has no usable record_timestamp",
        )

    try:
        detail, detail_state = get_version(sname, version_number)
    except Exception as exc:
        logger.warning(
            "Current-version detail fetch failed for %s (v%s): %s",
            sname,
            version_number,
            exc,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            reason="detail fetch failed",
        )

    if not isinstance(detail, dict):
        logger.warning(
            "Current-version detail unavailable for %s (v%s): expected dict, got %s",
            sname,
            version_number,
            type(detail).__name__,
        )
        return GWFlowCurrentVersion(
            available=False,
            versions_state=versions_state,
            detail_state=detail_state,
            reason="detail response is not a dict",
        )

    raw_payload = detail.get("raw_payload")
    if raw_payload is not None and not isinstance(raw_payload, dict):
        logger.warning(
            "Current-version detail unavailable for %s (v%s): raw_payload is not an object or null",
            sname,
            version_number,
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
            "Current-version %s (v%s) has no usable finite trigger time; "
            "the version identity is still authoritative and any stored trigger time is preserved",
            sname,
            version_number,
        )
        trigger_time = None
    else:
        trigger_time = float(trigger_time)

    return GWFlowCurrentVersion(
        available=True,
        trigger_time=trigger_time,
        current_version_number=version_number,
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
