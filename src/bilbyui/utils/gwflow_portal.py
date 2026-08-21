import logging

import requests
from django.conf import settings
from django.core.cache import caches

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
