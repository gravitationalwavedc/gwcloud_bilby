from types import SimpleNamespace
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, ExternalBilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import upload_external_bilby_job


class TestUploadExternalBilbyJob(BilbyTestCase):
    def setUp(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.details = SimpleNamespace(name="myjob", description="Test Description", private=False)
        self.ini_file = SimpleNamespace(name="job.ini")
        self.result_url = "https://www.example.com/"

    def _make_args(self, label="myjob"):
        return SimpleNamespace(label=label)

    @mock.patch("bilbyui.views._create_bilby_job_record")
    @mock.patch("bilbyui.views._strip_supporting_file_args")
    @mock.patch("bilbyui.views.prepare_args_for_data_input")
    @mock.patch("bilbyui.views.check_job_embargo_status")
    @mock.patch("bilbyui.views._parse_and_validate_ini")
    def test_success_creates_external_job_record(self, mock_parse, mock_embargo, mock_prepare, mock_strip, mock_create):
        args = self._make_args()
        mock_parse.return_value = args
        mock_embargo.return_value = False

        job = BilbyJob.objects.create(
            user=self.user,
            name=self.details.name,
            description=self.details.description,
            private=self.details.private,
            ini_string="",
            job_type=BilbyJobType.EXTERNAL,
        )
        mock_create.return_value = job

        result = upload_external_bilby_job(self.user, self.details, self.ini_file, self.result_url)

        self.assertIs(result, job)
        self.assertEqual(args.label, self.details.name)
        mock_create.assert_called_once_with(self.user, self.details, args, BilbyJobType.EXTERNAL)
        self.assertTrue(ExternalBilbyJob.objects.filter(job=job, url=self.result_url).exists())

    @mock.patch("bilbyui.views.check_job_embargo_status")
    @mock.patch("bilbyui.views._parse_and_validate_ini")
    def test_embargo_rejection_raises_permission_error(self, mock_parse, mock_embargo):
        mock_parse.return_value = self._make_args()
        mock_embargo.return_value = True

        with self.assertRaises(PermissionError):
            upload_external_bilby_job(self.user, self.details, self.ini_file, self.result_url)

        self.assertFalse(BilbyJob.objects.exists())
        self.assertFalse(ExternalBilbyJob.objects.exists())

    @mock.patch("bilbyui.views.check_job_embargo_status")
    @mock.patch("bilbyui.views._parse_and_validate_ini")
    def test_invalid_job_name_rejected(self, mock_parse, mock_embargo):
        mock_parse.return_value = self._make_args()
        mock_embargo.return_value = False
        self.details.name = "Bad Name$"

        with self.assertRaises(ValueError):
            upload_external_bilby_job(self.user, self.details, self.ini_file, self.result_url)

        self.assertFalse(BilbyJob.objects.exists())
        self.assertFalse(ExternalBilbyJob.objects.exists())
