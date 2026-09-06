import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from bilbyui.models import BilbyJob, SupportingFile
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import upload_supporting_files


class TestUploadSupportingFiles(BilbyTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.create_user(id=1234)

    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.upload_dir = Path(self.tmp_dir.name) / "supporting_files"

        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def _make_supporting_file(self):
        return SupportingFile.objects.create(
            job=self.job,
            file_type=SupportingFile.PSD,
            file_name="test.psd",
            upload_token=uuid.uuid4(),
        )

    def _uploaded_file(self, content=b"test content"):
        return SimpleUploadedFile(name="test.psd", content=content)

    def _call(self, supporting_files, uploaded_files):
        with override_settings(SUPPORTING_FILE_UPLOAD_DIR=str(self.upload_dir)):
            return upload_supporting_files(supporting_files, uploaded_files)

    @patch("bilbyui.models.submit_job")
    def test_creates_job_dir_and_writes_file_and_clears_token(self, mock_submit_job):
        mock_submit_job.return_value = {"jobId": 4321}
        supporting_file = self._make_supporting_file()
        content = b"some chunked content"

        result = self._call([supporting_file], [self._uploaded_file(content)])

        self.assertTrue(result)

        job_dir = self.upload_dir / str(self.job.id)
        self.assertTrue(job_dir.is_dir())

        written = (job_dir / str(supporting_file.id)).read_bytes()
        self.assertEqual(written, content)

        supporting_file.refresh_from_db()
        self.assertIsNone(supporting_file.upload_token)

    @patch("bilbyui.models.submit_job")
    def test_submits_job_when_all_files_uploaded(self, mock_submit_job):
        mock_submit_job.return_value = {"jobId": 4321}
        supporting_file = self._make_supporting_file()

        self._call([supporting_file], [self._uploaded_file()])

        self.job.refresh_from_db()
        self.assertEqual(self.job.job_controller_id, 4321)

    @patch("bilbyui.models.submit_job")
    def test_does_not_submit_job_when_files_remain(self, mock_submit_job):
        uploaded = self._make_supporting_file()
        remaining = self._make_supporting_file()

        self._call([uploaded], [self._uploaded_file()])

        mock_submit_job.assert_not_called()
        self.job.refresh_from_db()
        self.assertIsNone(self.job.job_controller_id)

        remaining.refresh_from_db()
        self.assertIsNotNone(remaining.upload_token)
