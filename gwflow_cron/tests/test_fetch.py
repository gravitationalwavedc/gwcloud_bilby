import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import responses

import settings
from fetch import MD5Mismatch, _get, fetch_to_staging
from job_controller import FetchError, JobControllerClient

API_URL = "https://jobcontroller.example.com/job/apiv1"
JWT_SECRET = "test-secret-that-is-longer-than-thirty-two-bytes"
USER_ID = 42


def _record(**overrides):
    rec = {
        "id": 1,
        "sname": "S260101a",
        "analysis_uid": "a1b2c3d4",
        "path": "/data/pe1/result.hdf5",
        "file_name": "result.hdf5",
        "md5_sum": "",
    }
    rec.update(overrides)
    return rec


def _md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _staged(base: Path, rec) -> Path:
    remote = rec["path"].removeprefix("CIT:")
    return base / rec["sname"] / rec["analysis_uid"] / remote.lstrip("/")


class TestGetHelper(unittest.TestCase):
    def test_dict_with_key_returns_value(self):
        self.assertEqual(_get({"path": "/x"}, "path"), "/x")

    def test_dict_missing_key_returns_none(self):
        self.assertIsNone(_get({"path": "/x"}, "missing"))

    def test_object_with_attribute_returns_value(self):
        rec = SimpleNamespace(path="/x")
        self.assertEqual(_get(rec, "path"), "/x")

    def test_object_without_attribute_raises_attribute_error(self):
        rec = SimpleNamespace(path="/x")
        with self.assertRaises(AttributeError):
            _get(rec, "missing")


class TestFetchToStaging(unittest.TestCase):
    def setUp(self):
        self.client = JobControllerClient(API_URL, JWT_SECRET, user_id=USER_ID, cluster="cit", bundle="test-bundle")

    def _mock_create(self, file_id="abc"):
        responses.add(
            responses.POST,
            f"{API_URL}/file/",
            json={"fileIds": [file_id]},
            status=200,
        )

    def _mock_get(self, file_id, content):
        responses.add(
            responses.GET,
            f"{API_URL}/file/?fileId={file_id}",
            body=content,
            status=200,
            content_type="application/octet-stream",
        )

    @responses.activate
    def test_happy_path_stages_file_and_returns_path(self):
        content = b"binary payload \x00\x01\x02"
        rec = _record(md5_sum=_md5(content))
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            result = fetch_to_staging(self.client, rec)
            self.assertEqual(result, _staged(Path(tmp), rec))
            self.assertEqual(result.read_bytes(), content)

    @responses.activate
    def test_cit_prefix_stripped_for_post_and_staged_location(self):
        content = b"data"
        rec = _record(path="CIT:/home/u/x.h5", md5_sum=_md5(content))
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            result = fetch_to_staging(self.client, rec)
            self.assertEqual(result, Path(tmp) / "S260101a" / "a1b2c3d4" / "home" / "u" / "x.h5")
            self.assertEqual(result.read_bytes(), content)
            body = json.loads(responses.calls[0].request.body)
            self.assertEqual(body["paths"], ["/home/u/x.h5"])

    @responses.activate
    def test_md5_mismatch_raises_and_removes_staged_file(self):
        content = b"data"
        rec = _record(md5_sum="0" * 32)
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            dest = _staged(Path(tmp), rec)
            with self.assertRaises(MD5Mismatch):
                fetch_to_staging(self.client, rec)
            self.assertFalse(dest.exists())

    @responses.activate
    def test_empty_md5_sum_skips_verification(self):
        content = b"data"
        rec = _record(md5_sum="")
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            result = fetch_to_staging(self.client, rec)
            self.assertEqual(result.read_bytes(), content)

    @responses.activate
    def test_fetch_error_on_post_propagates_and_creates_no_dir(self):
        responses.add(responses.POST, f"{API_URL}/file/", status=404, body="missing")

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            with self.assertRaises(FetchError):
                fetch_to_staging(self.client, _record())
            self.assertFalse((Path(tmp) / "S260101a").exists())

    @responses.activate
    def test_fetch_error_on_get_propagates_and_no_dest_file(self):
        self._mock_create()
        responses.add(responses.GET, f"{API_URL}/file/?fileId=abc", status=404, body="gone")

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            rec = _record()
            dest = _staged(Path(tmp), rec)
            with self.assertRaises(FetchError):
                fetch_to_staging(self.client, rec)
            self.assertFalse(dest.exists())

    @responses.activate
    def test_staging_dirs_created_nested(self):
        content = b"data"
        rec = _record(path="CIT:/a/b/c/d.h5", md5_sum=_md5(content))
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            result = fetch_to_staging(self.client, rec)
            self.assertTrue(result.parent.is_dir())
            self.assertEqual(result.read_bytes(), content)

    @responses.activate
    def test_staging_dir_override_is_honored(self):
        content = b"data"
        rec = _record(md5_sum=_md5(content))
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = str(Path(tmp) / "default")
            with TemporaryDirectory() as override:
                result = fetch_to_staging(self.client, rec, staging_dir=override)
                self.assertTrue(str(result).startswith(override))
                self.assertEqual(result.read_bytes(), content)
                self.assertFalse((Path(tmp) / "default").exists())

    @responses.activate
    def test_object_record_supported(self):
        content = b"data"
        rec = SimpleNamespace(**_record(md5_sum=_md5(content)))
        self._mock_create()
        self._mock_get("abc", content)

        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            result = fetch_to_staging(self.client, rec)
            self.assertEqual(result.read_bytes(), content)

    def test_traversal_remote_path_raises_and_leaves_no_file(self):
        rec = _record(path="CIT:/home/u/../../escape.txt")
        with TemporaryDirectory() as tmp:
            settings.STAGING_DIR = tmp
            with self.assertRaises(FetchError):
                fetch_to_staging(self.client, rec)
            self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_unsafe_sname_or_analysis_uid_raises(self):
        for overrides in (
            {"sname": "../../escape"},
            {"sname": "a/b"},
            {"sname": "S\x00X"},
            {"analysis_uid": "../x"},
            {"analysis_uid": "a/b"},
        ):
            with self.subTest(overrides=overrides):
                with TemporaryDirectory() as tmp:
                    settings.STAGING_DIR = tmp
                    with self.assertRaises(FetchError):
                        fetch_to_staging(self.client, _record(**overrides))
                    self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_none_sname_or_analysis_uid_raises_fetch_error(self):
        for overrides in ({"sname": None}, {"analysis_uid": None}):
            with self.subTest(overrides=overrides):
                with TemporaryDirectory() as tmp:
                    settings.STAGING_DIR = tmp
                    with self.assertRaises(FetchError):
                        fetch_to_staging(self.client, _record(**overrides))
                    self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_non_string_sname_or_analysis_uid_raises_fetch_error(self):
        for overrides in ({"sname": 123}, {"analysis_uid": ["a"]}):
            with self.subTest(overrides=overrides):
                with TemporaryDirectory() as tmp:
                    settings.STAGING_DIR = tmp
                    with self.assertRaises(FetchError):
                        fetch_to_staging(self.client, _record(**overrides))
                    self.assertEqual(list(Path(tmp).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
