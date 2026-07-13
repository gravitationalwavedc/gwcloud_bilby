from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, ExternalBilbyJob, FileDownloadToken
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_result_files


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBuildResultFiles(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user(id=1, name="buffy summers", primary_email="buffy@test.com")
        cls.ini = create_test_ini_string({"detectors": "['H1']"})

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
