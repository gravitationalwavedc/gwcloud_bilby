import logging
import os
from pathlib import Path
from urllib.parse import urljoin

import jwt
import requests

logger = logging.getLogger("gwflow_ingest.job_controller")


class ClusterOffline(Exception):
    pass


class FetchError(Exception):
    pass


class JobControllerClient:
    def __init__(
        self, api_url: str, jwt_secret: str, user_id: int = 0, cluster: str | None = None, bundle: str | None = None
    ):
        if not api_url or "://" not in api_url:
            raise ValueError("api_url must be a non-empty absolute URL")
        if not api_url.endswith("/"):
            api_url += "/"
        self.api_url = api_url
        self.jwt_secret = jwt_secret
        self.user_id = user_id
        self.cluster = cluster
        self.bundle = bundle

    def _mint_jwt(self) -> str:
        return jwt.encode({"userId": self.user_id}, self.jwt_secret, algorithm="HS256")

    def create_file_downloads(self, paths: list[str]) -> list[str]:
        url = urljoin(self.api_url, "file/")
        headers = {"Authorization": f"Bearer {self._mint_jwt()}"}
        body = {"cluster": self.cluster, "bundle": self.bundle, "paths": paths}
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code != 200:
            raise FetchError(f"create_file_downloads failed with status {resp.status_code}: {resp.text}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise FetchError(f"create_file_downloads returned malformed response: {resp.text}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("fileIds"), list) or not data["fileIds"]:
            raise FetchError(f"create_file_downloads returned malformed response: {resp.text}")
        return data["fileIds"]

    def download(self, file_id: str, dest: Path) -> None:
        url = urljoin(self.api_url, "file/")
        headers = {"Authorization": f"Bearer {self._mint_jwt()}"}
        part = str(dest) + ".part"
        try:
            with requests.get(url, params={"fileId": file_id}, headers=headers, stream=True, timeout=(10, 300)) as resp:
                if resp.status_code == 503:
                    raise ClusterOffline(f"cluster offline (HTTP {resp.status_code}): {resp.text}")
                if resp.status_code != 200:
                    raise FetchError(f"download failed with status {resp.status_code}: {resp.text}")
                with open(part, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
            os.replace(part, dest)
        except Exception:
            if os.path.exists(part):
                os.remove(part)
            raise

    def map_remote_path(self, path: str) -> str:
        if not isinstance(path, str):
            raise FetchError(f"unsafe remote path {path!r}: not a string")
        mapped = path.removeprefix("CIT:")
        if not mapped.startswith("/"):
            raise FetchError(f"unsafe remote path {path!r}: not an absolute path")
        if "\x00" in mapped or ".." in mapped.split("/"):
            raise FetchError(f"unsafe remote path {path!r}: contains a '..' segment or NUL byte")
        return mapped
