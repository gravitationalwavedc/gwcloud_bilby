import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import jwt
import requests
import responses

from job_controller import ClusterOffline, FetchError, JobControllerClient

API_URL = "https://jobcontroller.example.com/job/apiv1"
JWT_SECRET = "test-secret-that-is-longer-than-thirty-two-bytes"
USER_ID = 42


class ExplodingReader(io.BufferedReader):
    def __init__(self):
        super().__init__(io.BytesIO(b""))
        self._reads = 0

    def read(self, size=-1):
        self._reads += 1
        raise requests.ConnectionError("connection reset mid-read")


class TestJobControllerClient(unittest.TestCase):
    def setUp(self):
        self.client = JobControllerClient(API_URL, JWT_SECRET, user_id=USER_ID, cluster="cit", bundle="test-bundle")

    def _file_url(self, file_id):
        return f"{API_URL}/file/?fileId={file_id}"

    def _auth_token(self, call):
        return call.request.headers["Authorization"].split(" ", 1)[1]

    @responses.activate
    def test_create_file_downloads_posts_body_with_jwt_and_returns_file_ids_in_order(self):
        paths = ["/data/pe1/config.ini", "/data/pe1/result.hdf5"]
        file_ids = ["a1a1a1a1-0000-4000-8000-000000000001", "b2b2b2b2-0000-4000-8000-000000000002"]
        responses.add(
            responses.POST,
            f"{API_URL}/file/",
            json={"fileIds": file_ids},
            status=200,
        )

        result = self.client.create_file_downloads(paths)

        self.assertEqual(result, file_ids)
        self.assertEqual(len(responses.calls), 1)
        call = responses.calls[0]
        self.assertTrue(call.request.headers["Authorization"].startswith("Bearer "))
        token = self._auth_token(call)
        claims = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual(claims["userId"], USER_ID)
        self.assertEqual(jwt.get_unverified_header(token)["alg"], "HS256")
        body = json.loads(call.request.body)
        self.assertEqual(body["cluster"], "cit")
        self.assertEqual(body["bundle"], "test-bundle")
        self.assertEqual(body["paths"], paths)

    @responses.activate
    def test_create_file_downloads_raises_fetch_error_on_non_200(self):
        responses.add(responses.POST, f"{API_URL}/file/", status=500, body="controller exploded")

        with self.assertRaises(FetchError) as ctx:
            self.client.create_file_downloads(["/data/pe1/config.ini"])
        self.assertIn("controller exploded", str(ctx.exception))

    @responses.activate
    def test_create_file_downloads_raises_fetch_error_on_malformed_200_body(self):
        for payload in (
            {"error": "internal error"},
            ["a1a1a1a1-0000-4000-8000-000000000001"],
            "not json",
        ):
            with self.subTest(payload=payload):
                responses.reset()
                if payload == "not json":
                    responses.add(responses.POST, f"{API_URL}/file/", body="not json", status=200)
                else:
                    responses.add(responses.POST, f"{API_URL}/file/", json=payload, status=200)
                with self.assertRaises(FetchError):
                    self.client.create_file_downloads(["/data/pe1/config.ini"])

    @responses.activate
    def test_create_file_downloads_raises_fetch_error_on_empty_file_ids(self):
        responses.add(responses.POST, f"{API_URL}/file/", json={"fileIds": []}, status=200)

        with self.assertRaises(FetchError):
            self.client.create_file_downloads(["/data/pe1/config.ini"])

    @responses.activate
    def test_download_streams_bytes_to_dest_via_part_file(self):
        content = b"a" * (3 * 1024 * 1024)
        responses.add(
            responses.GET,
            self._file_url("abc"),
            body=content,
            status=200,
            content_type="application/octet-stream",
        )

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "result.hdf5"
            self.client.download("abc", dest)
            self.assertEqual(dest.read_bytes(), content)
            self.assertFalse(Path(str(dest) + ".part").exists())
        self.assertTrue(responses.calls[0].request.headers["Authorization"].startswith("Bearer "))

    @responses.activate
    def test_download_raises_cluster_offline_on_503(self):
        responses.add(responses.GET, self._file_url("abc"), status=503, body="cluster offline for maintenance")

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "result.hdf5"
            with self.assertRaises(ClusterOffline):
                self.client.download("abc", dest)
            self.assertFalse(Path(str(dest) + ".part").exists())

    @responses.activate
    def test_download_raises_fetch_error_on_other_non_200_and_removes_part(self):
        responses.add(responses.GET, self._file_url("abc"), status=404, body="file not found on controller")

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "result.hdf5"
            with self.assertRaises(FetchError) as ctx:
                self.client.download("abc", dest)
            self.assertIn("file not found on controller", str(ctx.exception))
            self.assertFalse(Path(str(dest) + ".part").exists())

    @responses.activate
    def test_download_removes_part_on_streaming_exception(self):
        responses.add(responses.GET, self._file_url("abc"), body=ExplodingReader(), status=200)

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "result.hdf5"
            with self.assertRaises(requests.exceptions.RequestException):
                self.client.download("abc", dest)
            self.assertFalse(Path(str(dest) + ".part").exists())

    def test_map_remote_path_strips_cit_prefix_and_passes_others_through(self):
        self.assertEqual(self.client.map_remote_path("CIT:/data/pe1/result.hdf5"), "/data/pe1/result.hdf5")
        self.assertEqual(self.client.map_remote_path("/data/pe1/result.hdf5"), "/data/pe1/result.hdf5")

    def test_map_remote_path_rejects_dotdot_nul_and_non_absolute(self):
        for bad in [
            "/data/../escape.txt",
            "CIT:/home/u/../../escape.txt",
            "/data/\x00escape.txt",
            "data/pe1/result.hdf5",
            "CIT:data/pe1/result.hdf5",
        ]:
            with self.subTest(path=bad):
                with self.assertRaises(FetchError):
                    self.client.map_remote_path(bad)

    def test_map_remote_path_rejects_non_string_path(self):
        for bad in [None, 12345, ["/data/pe1/result.hdf5"], {"path": "/data/pe1/result.hdf5"}]:
            with self.subTest(path=bad):
                with self.assertRaises(FetchError):
                    self.client.map_remote_path(bad)

    def test_map_remote_path_allows_dot_prefix_and_trailing_slash(self):
        self.assertEqual(self.client.map_remote_path("/data/.hidden/file.h5"), "/data/.hidden/file.h5")
        self.assertEqual(self.client.map_remote_path("/data/pe1/"), "/data/pe1/")

    def test_init_raises_value_error_on_empty_or_schemeless_api_url(self):
        with self.assertRaises(ValueError):
            JobControllerClient("", JWT_SECRET, user_id=USER_ID, cluster="cit", bundle="test-bundle")
        with self.assertRaises(ValueError):
            JobControllerClient(
                "jobcontroller.example.com/job/apiv1", JWT_SECRET, user_id=USER_ID, cluster="cit", bundle="test-bundle"
            )


if __name__ == "__main__":
    unittest.main()
