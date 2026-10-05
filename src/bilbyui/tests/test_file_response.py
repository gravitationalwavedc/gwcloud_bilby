import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from bilbyui.models import BilbyJob, FileDownloadToken, SupportingFile
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _file_response


class _Request:
    def __init__(self, get):
        self.GET = get


class FileResponseHelperTestCase(BilbyTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "data.txt"
        self.file_path.write_bytes(b"file contents")

    def test_inline_by_default(self):
        response = _file_response(_Request({}), self.file_path, "data.txt")
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'inline; filename="data.txt"',
        )

    def test_attachment_with_force_download(self):
        response = _file_response(_Request({"forceDownload": ""}), self.file_path, "data.txt")
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="data.txt"',
        )


@override_settings(EMBARGO_START_TIME=100.0)
class BilbyCapabilityTokenGateTestCase(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_user()
        self.other_user = self.create_user(id=22)
        self.job_dir = TemporaryDirectory()
        self.supporting_dir = TemporaryDirectory()
        self.addCleanup(self.job_dir.cleanup)
        self.addCleanup(self.supporting_dir.cleanup)

    @staticmethod
    def response_triple(response):
        return response.status_code, response.content, sorted(response.headers.items())

    def create_job(self, *, private=False, trigger_time=99.0):
        job = BilbyJob.objects.create(
            user=self.owner,
            name=f"token-job-{BilbyJob.objects.count()}",
            private=private,
            trigger_time=trigger_time,
            ini_string="",
        )
        BilbyJob.objects.filter(pk=job.pk).update(trigger_time=trigger_time)
        return job

    def missing_response(self):
        return self.client.get(f"{reverse('file_download')}?fileId={uuid.uuid4()}")

    def test_file_download_token_reauthorizes_stale_owner_before_path_work(self):
        job = self.create_job()
        token = FileDownloadToken.objects.create(
            job=job,
            path="/known-result.h5",
        )
        BilbyJob.objects.filter(pk=job.pk).update(trigger_time=100.0)

        with (
            patch(
                "bilbyui.models.BilbyJob.get_upload_directory",
                autospec=True,
            ) as get_upload_directory,
            patch("bilbyui.views.Path") as path_probe,
            patch("bilbyui.views._file_response") as file_response,
        ):
            denied = self.client.get(f"{reverse('file_download')}?fileId={token.token}")

        missing = self.missing_response()
        self.assertEqual(self.response_triple(denied), self.response_triple(missing))
        self.assertNotIn("Content-Disposition", denied.headers)
        self.assertNotIn(b"known-result.h5", denied.content)
        get_upload_directory.assert_not_called()
        path_probe.assert_not_called()
        file_response.assert_not_called()

    def test_supporting_file_token_reauthorizes_stale_owner_before_path_work(self):
        job = self.create_job()
        supporting_file = SupportingFile.objects.create(
            job=job,
            file_type=SupportingFile.PRIOR,
            file_name="known-prior.json",
            upload_token=None,
        )
        BilbyJob.objects.filter(pk=job.pk).update(trigger_time=100.0)

        with (
            override_settings(SUPPORTING_FILE_UPLOAD_DIR=self.supporting_dir.name),
            patch("bilbyui.views.Path") as path_probe,
            patch("bilbyui.views._file_response") as file_response,
        ):
            denied = self.client.get(f"{reverse('file_download')}?fileId={supporting_file.download_token}")

        missing = self.missing_response()
        self.assertEqual(self.response_triple(denied), self.response_triple(missing))
        self.assertNotIn("Content-Disposition", denied.headers)
        self.assertNotIn(b"known-prior.json", denied.content)
        path_probe.assert_not_called()
        file_response.assert_not_called()

    def test_file_download_token_composes_private_scope_with_visibility(self):
        job = self.create_job(private=True)
        token = FileDownloadToken.objects.create(job=job, path="/result.h5")

        anonymous_denied = self.client.get(f"{reverse('file_download')}?fileId={token.token}")
        self.authenticate(user=self.owner)
        with override_settings(JOB_UPLOAD_DIR=self.job_dir.name):
            upload_directory = job.get_upload_directory()
            upload_directory.mkdir(parents=True)
            (upload_directory / "result.h5").write_bytes(b"result")
            owner_response = self.client.get(f"{reverse('file_download')}?fileId={token.token}")

        self.assertEqual(anonymous_denied.status_code, 404)
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(b"".join(owner_response.streaming_content), b"result")

        BilbyJob.objects.filter(pk=job.pk).update(trigger_time=100.0)
        owner_embargo_denied = self.client.get(f"{reverse('file_download')}?fileId={token.token}")
        self.assertEqual(
            self.response_triple(owner_embargo_denied),
            self.response_triple(self.missing_response()),
        )

    def test_supporting_file_token_denies_other_user_private_owner(self):
        job = self.create_job(private=True)
        supporting_file = SupportingFile.objects.create(
            job=job,
            file_type=SupportingFile.DATA,
            file_name="private-data.gwf",
            upload_token=None,
        )
        self.authenticate(user=self.other_user)

        with (
            patch("bilbyui.views.Path") as path_probe,
            patch("bilbyui.views._file_response") as file_response,
        ):
            denied = self.client.get(f"{reverse('file_download')}?fileId={supporting_file.download_token}")

        self.assertEqual(
            self.response_triple(denied),
            self.response_triple(self.missing_response()),
        )
        path_probe.assert_not_called()
        file_response.assert_not_called()
