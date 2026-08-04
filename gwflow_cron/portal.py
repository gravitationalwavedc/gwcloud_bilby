import logging
import time
from urllib.parse import urljoin

import requests

logger = logging.getLogger("gwflow_ingest.portal")


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
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp
                logger.warning(f"Portal request attempt {attempt} failed with status {resp.status_code}")
            except (requests.RequestException, Exception) as e:
                if attempt == max_attempts:
                    raise
                logger.warning(f"Portal request attempt {attempt} raised exception: {e}")
            time.sleep(backoff)
            backoff *= 2.0
        raise RuntimeError("Unreachable retry loop end")

    def iter_changed(self, since: str | None = None, page_size: int = 50):
        url = urljoin(self.base_url, "api/v1/superevents/")
        params = {"ordering": "commit_timestamp,sname"}
        if since:
            params["commit_timestamp__gte"] = since
        if page_size:
            params["page_size"] = str(page_size)

        while url:
            resp = self._request_with_retry("GET", url, params=params)
            data = resp.json()
            if isinstance(data, dict):
                results = data.get("results", [])
                next_url = data.get("next")
            else:
                results = data
                next_url = None

            # Sort rows on page by (commit_timestamp, sname)
            sorted_results = sorted(
                results,
                key=lambda x: (
                    x.get("commit_timestamp", "") if isinstance(x, dict) else "",
                    x.get("sname", "") if isinstance(x, dict) else "",
                ),
            )
            yield from sorted_results

            url = next_url
            params = None  # Subsequent page URLs include query parameters

    def get_superevent(self, sname: str) -> dict:
        url = urljoin(self.base_url, f"api/v1/superevents/{sname}/")
        resp = self._request_with_retry("GET", url)
        return resp.json()

    def iter_current_snames(self):
        url = urljoin(self.base_url, "api/v1/superevents/")
        while url:
            resp = self._request_with_retry("GET", url)
            data = resp.json()
            if isinstance(data, dict):
                results = data.get("results", [])
                next_url = data.get("next")
            else:
                results = data
                next_url = None

            for row in results:
                if isinstance(row, dict):
                    if "sname" in row:
                        yield row["sname"]
                elif isinstance(row, str):
                    yield row

            url = next_url
