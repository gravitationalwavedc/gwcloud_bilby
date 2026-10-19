import logging
import time
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger("gwflow_ingest.portal")

_ENVELOPE_FIELDS = {"count", "next", "previous", "results"}
_DETAIL_COLLECTION_FIELDS = (
    "analyses",
    "detector_configurations",
    "gracedb_events",
    "catalog_connections",
)


class PortalMalformedResponseError(Exception):
    """Raised when a successful portal response violates the API contract."""

    def __init__(
        self,
        endpoint: str,
        correlation_context: tuple[str, str | None, str],
        reason: str,
    ):
        self.endpoint = endpoint
        self.correlation_context = correlation_context
        self.reason = reason
        super().__init__(
            f"Malformed portal response from {endpoint}: {reason}; correlation_context={correlation_context!r}"
        )


class PortalClient:
    def __init__(self, base_url: str, token: str):
        if not base_url.endswith("/"):
            base_url += "/"
        self.base_url = base_url
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": token})

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        max_attempts = 3
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.session.request(method, url, timeout=10, **kwargs)
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp
                if attempt == max_attempts:
                    resp.raise_for_status()
                logger.warning(
                    "Portal request attempt %s failed with status %s",
                    attempt,
                    resp.status_code,
                )
            except requests.HTTPError:
                raise
            except Exception as e:
                if attempt == max_attempts:
                    raise
                logger.warning("Portal request attempt %s raised exception: %s", attempt, e)
            time.sleep(backoff)
            backoff *= 2.0

    def _malformed(
        self,
        endpoint: str,
        sname: str | None,
        operation: str,
        reason: str,
    ) -> PortalMalformedResponseError:
        context = (endpoint, sname, operation)
        error = PortalMalformedResponseError(endpoint, context, reason)
        logger.error(
            "Malformed portal response endpoint=%s correlation_context=%r reason=%s",
            endpoint,
            context,
            reason,
        )
        return error

    def _parse_json(
        self,
        response: requests.Response,
        endpoint: str,
        sname: str | None,
        operation: str,
    ):
        try:
            return response.json()
        except ValueError as exc:
            raise self._malformed(
                endpoint,
                sname,
                operation,
                f"response body is not valid JSON: {exc}",
            ) from exc

    def _validate_envelope(
        self,
        data,
        endpoint: str,
        sname: str | None,
        operation: str,
    ) -> dict:
        if not isinstance(data, dict):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "collection response must be an object",
            )

        actual_fields = set(data)
        if actual_fields != _ENVELOPE_FIELDS:
            missing = sorted(_ENVELOPE_FIELDS - actual_fields)
            unexpected = sorted(actual_fields - _ENVELOPE_FIELDS)
            raise self._malformed(
                endpoint,
                sname,
                operation,
                f"collection envelope fields are invalid (missing={missing}, unexpected={unexpected})",
            )

        if isinstance(data["count"], bool) or not isinstance(data["count"], int):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "collection envelope count must be an integer",
            )
        if data["next"] is not None and not isinstance(data["next"], str):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "collection envelope next must be a URL string or null",
            )
        if data["previous"] is not None and not isinstance(data["previous"], str):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "collection envelope previous must be a URL string or null",
            )
        if not isinstance(data["results"], list):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "collection envelope results must be an array",
            )
        return data

    def _iter_pages(
        self,
        url: str,
        params: dict | None = None,
        *,
        sname: str | None = None,
        operation: str = "list",
    ):
        visited = set()
        base_origin = urlparse(self.base_url)[:2]
        while url:
            endpoint = url
            if endpoint in visited:
                raise self._malformed(
                    endpoint,
                    sname,
                    operation,
                    "pagination next URL forms a cycle",
                )
            visited.add(endpoint)

            resp = self._request_with_retry("GET", endpoint, params=params)
            data = self._parse_json(resp, endpoint, sname, operation)
            envelope = self._validate_envelope(data, endpoint, sname, operation)

            yield envelope["results"], envelope["next"]

            next_url = envelope["next"]
            if next_url is not None:
                next_url = urljoin(endpoint, next_url)
                if urlparse(next_url)[:2] != base_origin:
                    raise self._malformed(
                        next_url,
                        sname,
                        operation,
                        "pagination next URL must have the portal origin",
                    )
            url = next_url
            params = None  # Subsequent page URLs include query parameters

    def iter_changed(self, since: str | None = None):
        url = urljoin(self.base_url, "api/v1/superevents/")
        for results, _ in self._iter_pages(url, {"page": 1}):
            for row in results:
                if not isinstance(row, dict):
                    raise self._malformed(
                        url,
                        None,
                        "changed",
                        "result row must be an object",
                    )
                record_timestamp = row.get("record_timestamp")
                row_sname = row.get("sname")
                if not isinstance(record_timestamp, str) or not record_timestamp:
                    raise self._malformed(
                        url,
                        row_sname if isinstance(row_sname, str) else None,
                        "changed",
                        "result row must have a non-empty string record_timestamp",
                    )
                if since is None or record_timestamp >= since:
                    yield row

    def _validate_detail(
        self,
        data,
        endpoint: str,
        sname: str,
        operation: str,
    ) -> dict:
        if not isinstance(data, dict):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "detail response must be an object",
            )

        for field in ("sname", "record_timestamp", "commit_sha"):
            if not isinstance(data.get(field), str) or not data[field]:
                raise self._malformed(
                    endpoint,
                    sname,
                    operation,
                    f"detail response field {field!r} must be a non-empty string",
                )

        if not isinstance(data.get("libraries"), list):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "detail response field 'libraries' must be an array",
            )

        version_number = data.get("version_number")
        if isinstance(version_number, bool) or not isinstance(version_number, int):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "detail response field 'version_number' must be an integer",
            )

        # Portal booleans may be strings such as "true", "1", or "yes".
        if not isinstance(data.get("is_current"), (bool, str)):
            raise self._malformed(
                endpoint,
                sname,
                operation,
                "detail response field 'is_current' must be a boolean or string",
            )

        for field in _DETAIL_COLLECTION_FIELDS:
            if field not in data:
                raise self._malformed(
                    endpoint,
                    sname,
                    operation,
                    f"detail response is missing required array field {field!r}",
                )
            if not isinstance(data[field], list):
                raise self._malformed(
                    endpoint,
                    sname,
                    operation,
                    f"detail response field {field!r} must be an array",
                )

        if "raw_payload" in data and data["raw_payload"] is not None:
            if not isinstance(data["raw_payload"], dict):
                raise self._malformed(
                    endpoint,
                    sname,
                    operation,
                    "detail response field 'raw_payload' must be an object or null",
                )

        return data

    def get_superevent(self, sname: str) -> dict:
        url = urljoin(self.base_url, f"api/v1/superevents/{sname}/")
        resp = self._request_with_retry("GET", url)
        data = self._parse_json(resp, url, sname, "current-detail")
        return self._validate_detail(data, url, sname, "current-detail")

    def get_versions(self, sname: str) -> list:
        """Return every canonical version summary page in server order."""
        url = urljoin(self.base_url, f"api/v1/superevents/{sname}/versions/")
        versions = []
        for results, _ in self._iter_pages(
            url,
            sname=sname,
            operation="versions",
        ):
            versions.extend(results)
        return versions

    def iter_current_snames(self):
        url = urljoin(self.base_url, "api/v1/superevents/")
        for results, _ in self._iter_pages(
            url,
            operation="current-snames",
        ):
            for row in results:
                if not isinstance(row, dict) or not isinstance(row.get("sname"), str):
                    row_keys = sorted(row.keys()) if isinstance(row, dict) else None
                    logger.error(
                        "Skipping malformed current-sname row endpoint=%s correlation_context=%r row_type=%s row_keys=%r",
                        url,
                        (url, None, "current-snames"),
                        type(row).__name__,
                        row_keys,
                    )
                    continue
                yield row["sname"]
