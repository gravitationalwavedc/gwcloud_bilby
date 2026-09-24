from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, ExternalBilbyJob, FileDownloadToken
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_result_file_entries, _build_result_files, _safe_external_url


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBuildResultFiles(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})
        cls.user = cls.create_user()

    def setUp(self):
        self.create_user(id=1)

    def test_external_job_returns_url_entry(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="external_job",
            description="external",
            job_type=BilbyJobType.EXTERNAL,
            ini_string=self.ini,
        )
        external = ExternalBilbyJob.objects.create(job=job, url="https://example.com/results.tar.gz")

        result = _build_result_files(job)

        self.assertEqual(
            result,
            [
                {
                    "path": external.url,
                    "is_dir": False,
                    "file_size": None,
                    "download_token": None,
                    "link_url": "https://example.com/results.tar.gz",
                }
            ],
        )

    def test_failed_file_list_returns_empty(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="normal_job",
            description="normal",
            job_controller_id=1,
            ini_string=self.ini,
        )

        with mock.patch.object(BilbyJob, "get_file_list", return_value=(False, "error")):
            self.assertEqual(_build_result_files(job), [])

    def test_successful_file_list_returns_files_with_tokens(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="normal_job",
            description="normal",
            job_controller_id=1,
            ini_string=self.ini,
        )
        files = [
            {"path": "/dir", "isDir": True, "fileSize": 0},
            {"path": "/dir/file.txt", "isDir": False, "fileSize": 42},
        ]

        with mock.patch.object(BilbyJob, "get_file_list", return_value=(True, files)):
            result = _build_result_files(job)

        self.assertEqual(len(result), 2)
        self.assertEqual(
            result[0],
            {
                "path": "/dir",
                "is_dir": True,
                "file_size": 0,
                "download_token": None,
            },
        )
        self.assertEqual(result[1]["path"], "/dir/file.txt")
        self.assertFalse(result[1]["is_dir"])
        self.assertEqual(result[1]["file_size"], 42)
        self.assertIsNotNone(result[1]["download_token"])
        self.assertEqual(
            result[1]["download_token"],
            FileDownloadToken.objects.get(job=job, path="/dir/file.txt").token,
        )

    def test_only_non_directory_paths_receive_download_tokens(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="normal_job",
            description="normal",
            job_controller_id=1,
            ini_string=self.ini,
        )
        files = [
            {"path": "/a.txt", "isDir": False, "fileSize": 1},
            {"path": "/b.txt", "isDir": False, "fileSize": 2},
        ]

        with mock.patch.object(BilbyJob, "get_file_list", return_value=(True, files)):
            _build_result_files(job)

        self.assertEqual(FileDownloadToken.objects.filter(job=job).count(), 2)
        self.assertEqual(
            set(FileDownloadToken.objects.filter(job=job).values_list("path", flat=True)),
            {"/a.txt", "/b.txt"},
        )

    def test_malformed_file_entry_missing_keys_does_not_crash(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="normal_job",
            description="normal",
            job_controller_id=1,
            ini_string=self.ini,
        )
        files = [
            {"path": "/dir", "isDir": True, "fileSize": 0},
            {},
            {"path": "/file.txt"},
        ]

        with mock.patch.object(BilbyJob, "get_file_list", return_value=(True, files)):
            result = _build_result_files(job)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["path"], "/dir")
        self.assertEqual(result[1], {"path": "", "is_dir": False, "file_size": 0, "download_token": None})
        self.assertEqual(result[2]["path"], "/file.txt")
        self.assertFalse(result[2]["is_dir"])
        self.assertEqual(result[2]["file_size"], 0)

    def test_non_dict_file_entries_are_skipped(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="normal_job",
            description="normal",
            job_controller_id=1,
            ini_string=self.ini,
        )
        files = [
            {"path": "/dir/file.txt", "isDir": False, "fileSize": 42},
            "not-a-dict",
            None,
        ]

        with mock.patch.object(BilbyJob, "get_file_list", return_value=(True, files)):
            result = _build_result_files(job)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "/dir/file.txt")
        self.assertEqual(result[0]["file_size"], 42)
        self.assertEqual(FileDownloadToken.objects.filter(job=job).count(), 1)

    def test_external_job_with_no_external_record_returns_empty(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="external_job",
            description="external",
            job_type=BilbyJobType.EXTERNAL,
            ini_string=self.ini,
        )

        self.assertEqual(_build_result_file_entries(job), [])


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestSafeExternalUrl(BilbyTestCase):
    def test_plain_http_url_is_returned_unchanged(self):
        self.assertEqual(_safe_external_url("http://example.com/results.tar.gz"), "http://example.com/results.tar.gz")

    def test_plain_https_url_is_returned_unchanged(self):
        self.assertEqual(_safe_external_url("https://example.com/results.tar.gz"), "https://example.com/results.tar.gz")

    def test_javascript_scheme_is_sanitised(self):
        self.assertEqual(_safe_external_url("javascript:alert(1)"), "")

    def test_data_scheme_is_sanitised(self):
        self.assertEqual(_safe_external_url("data:text/html,<script>alert(1)</script>"), "")

    def test_ftp_scheme_is_sanitised(self):
        self.assertEqual(_safe_external_url("ftp://example.com/results.tar.gz"), "")

    def test_protocol_relative_url_is_sanitised(self):
        self.assertEqual(_safe_external_url("//example.com/results.tar.gz"), "")

    def test_http_scheme_with_empty_netloc_is_sanitised(self):
        self.assertEqual(_safe_external_url("http://"), "")

    def test_https_scheme_with_empty_netloc_is_sanitised(self):
        self.assertEqual(_safe_external_url("https://"), "")

    def test_empty_value_is_sanitised(self):
        self.assertEqual(_safe_external_url(""), "")

    def test_none_value_is_sanitised(self):
        self.assertEqual(_safe_external_url(None), "")
