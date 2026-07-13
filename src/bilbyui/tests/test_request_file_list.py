import os
from tempfile import TemporaryDirectory
from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.jobs.request_file_list import request_file_list


class TestRequestFileListUploaded(BilbyTestCase):
    def setUp(self):
        self.authenticate()

        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="TestUploaded",
            description="uploaded job",
            job_controller_id=None,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            job_type=BilbyJobType.UPLOADED,
        )

    @override_settings(IGNORE_ELASTIC_SEARCH=True, JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_valid_path_returns_files(self):
        job_dir = self.job.get_upload_directory()
        os.makedirs(os.path.join(job_dir, "data"), exist_ok=True)
        with open(os.path.join(job_dir, "data", "a.txt"), "w") as f:
            f.write("hi")

        success, file_list = request_file_list(self.job, "data", False)
        self.assertTrue(success)
        self.assertEqual(len(file_list), 1)
        self.assertEqual(file_list[0]["path"], "/data/a.txt")

    @override_settings(IGNORE_ELASTIC_SEARCH=True, JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_sibling_upload_dir_is_rejected(self):
        # job id 123 vs sibling dir 1234: "/uploads/1234/x".startswith("/uploads/123") is True
        job_dir = self.job.get_upload_directory()
        os.makedirs(job_dir, exist_ok=True)

        # Build a sibling directory that the buggy prefix check would accept
        sibling_dir = os.path.join(os.path.dirname(job_dir), f"{self.job.id}4")
        os.makedirs(sibling_dir, exist_ok=True)
        with open(os.path.join(sibling_dir, "secret.txt"), "w") as f:
            f.write("secret")

        # Requesting "../<id>4/..." must NOT disclose the sibling contents
        success, result = request_file_list(self.job, f"../{self.job.id}4", False)
        self.assertFalse(success)
        self.assertEqual(result, "Files do not exist")

    @override_settings(IGNORE_ELASTIC_SEARCH=True, JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_traversal_paths_rejected(self):
        job_dir = self.job.get_upload_directory()
        os.makedirs(job_dir, exist_ok=True)

        for bad_path in ["./data", "../data/", "../../bin/bash"]:
            success, result = request_file_list(self.job, bad_path, False)
            self.assertFalse(success, f"path {bad_path!r} should be rejected")
            self.assertEqual(result, "Files do not exist")

    @override_settings(IGNORE_ELASTIC_SEARCH=True, JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_empty_path_returns_job_dir(self):
        job_dir = self.job.get_upload_directory()
        os.makedirs(job_dir, exist_ok=True)

        success, file_list = request_file_list(self.job, "", False)
        self.assertTrue(success)
        self.assertEqual(file_list, [])

    @override_settings(IGNORE_ELASTIC_SEARCH=True, JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_recursive_listing_returns_all_entries(self):
        job_dir = self.job.get_upload_directory()
        os.makedirs(os.path.join(job_dir, "data", "sub"), exist_ok=True)
        with open(os.path.join(job_dir, "data", "sub", "b.txt"), "w") as f:
            f.write("b")
        # A broken symlink should be skipped (FileNotFoundError on stat)
        os.symlink(
            os.path.join(job_dir, "data", "sub", "missing"),
            os.path.join(job_dir, "data", "broken_link"),
        )

        success, file_list = request_file_list(self.job, "data", True)
        self.assertTrue(success)
        paths = sorted(entry["path"] for entry in file_list)
        self.assertIn("/data/sub", paths)
        self.assertIn("/data/sub/b.txt", paths)

    def test_non_uploaded_job_without_controller_id(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="TestNormal",
            description="normal job",
            job_controller_id=None,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            job_type=BilbyJobType.NORMAL,
        )

        success, result = request_file_list(job, "", False)
        self.assertFalse(success)
        self.assertEqual(result, "Job not submitted")

    @mock.patch("bilbyui.utils.jobs.request_file_list._make_job_controller_request")
    @mock.patch("bilbyui.utils.jobs.request_file_list.check_request_leak")
    def test_non_uploaded_job_controller_request(self, check_request_leak, make_request):
        make_request.return_value = {"files": [{"path": "/x", "isDir": False, "fileSize": 1}]}

        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="TestNormal2",
            description="normal job 2",
            job_controller_id=5,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            job_type=BilbyJobType.NORMAL,
        )

        success, result = request_file_list(job, "some/path", True, user_id=99)
        self.assertTrue(success)
        self.assertEqual(result, [{"path": "/x", "isDir": False, "fileSize": 1}])
        make_request.assert_called_once()
        args, kwargs = make_request.call_args
        self.assertEqual(args[2], 99)
        self.assertEqual(kwargs["data"]["path"], "some/path")
        self.assertTrue(kwargs["data"]["recursive"])

        # Exception path returns an error message
        make_request.side_effect = Exception("boom")
        success, result = request_file_list(job, "", False)
        self.assertFalse(success)
        self.assertEqual(result, "Error getting job file list")
