import uuid
from tempfile import TemporaryDirectory
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpRequest
from django.test import override_settings
from graphql import GraphQLResolveInfo
from graphql_relay import to_global_id

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, FileDownloadToken
from bilbyui.schema import BilbyJobNode, PublicBilbyJobFilter, Query
from bilbyui.status import JobStatus
from bilbyui.tests.test_utils import create_test_ini_string, silence_errors
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()
JOB_STATUS_QUERY = """
    query { bilbyJob(id:"%s") { jobStatus { name number date } } }
"""
RESULT_FILES_QUERY = """
    query { bilbyResultFiles(jobId: "%s") { files { path downloadToken } } }
"""
DOWNLOAD_IDS_MUTATION = """
    mutation($input: GenerateFileDownloadIdsInput!) {
        generateFileDownloadIds(input: $input) { result }
    }
"""


class TestSchemaCoverage(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        User.objects.update_or_create(id=1, defaults={"name": "u", "primary_email": "u@test.com"})
        self.job = BilbyJob.objects.create(
            user_id=1,
            name="T",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        self.global_id = to_global_id("BilbyJobNode", self.job.id)

    def test_public_bilby_job_filter_qs(self):
        request = HttpRequest()
        request.user = self.user
        self.assertGreaterEqual(PublicBilbyJobFilter(request=request, queryset=BilbyJob.objects.all()).qs.count(), 0)

    def test_resolve_gwclouduser(self):
        info = mock.Mock(spec=GraphQLResolveInfo)
        info.context = mock.Mock(user=self.user)
        self.assertEqual(Query.resolve_gwclouduser(Query(), info), self.user)

    def test_resolve_user_exception_fallback(self):
        parent = mock.Mock()
        parent.user = mock.Mock(spec=[])
        self.assertEqual(BilbyJobNode.resolve_user(parent, mock.Mock()), "Unknown User")

    @mock.patch("bilbyui.schema.generate_parameter_output", side_effect=Exception("fail"))
    def test_resolve_params_exception_returns_none(self, *_):
        self.assertIsNone(BilbyJobNode.resolve_params(mock.Mock(), mock.Mock()))

    @mock.patch("bilbyui.schema.request_job_filter", return_value=(None, [{"id": 1, "history": None}]))
    @mock.patch("bilbyui.schema.derive_job_status", side_effect=Exception("status unavailable"))
    def test_bilby_job_status_exception_fallback(self, *_):
        response = self.query(JOB_STATUS_QUERY % self.global_id)
        self.assertEqual(response.data["bilbyJob"]["jobStatus"], {"name": "Unknown", "number": 0, "date": "Unknown"})

    @mock.patch("bilbyui.schema.request_job_filter", side_effect=lambda *a, **k: (True, []))
    def test_bilby_job_status_uploaded(self, *_):
        self.job.job_type = BilbyJobType.UPLOADED
        self.job.save()
        status = self.query(JOB_STATUS_QUERY % self.global_id).data["bilbyJob"]["jobStatus"]
        self.assertEqual(status["name"], JobStatus.display_name(JobStatus.COMPLETED))
        self.assertEqual(status["number"], JobStatus.COMPLETED)
        self.assertEqual(status["date"], str(self.job.creation_time))

    @silence_errors
    @mock.patch("bilbyui.models.request_file_list", return_value=(False, "controller error"))
    def test_bilby_result_files_list_failure(self, *_):
        response = self.query(RESULT_FILES_QUERY % self.global_id)
        self.assertIsNone(response.data["bilbyResultFiles"])
        self.assertIn("Error getting file list", str(response.errors[0]["message"]))

    @silence_errors
    @mock.patch(
        "bilbyui.models.request_file_list", return_value=(True, [{"path": "/f.txt", "isDir": False, "fileSize": 1}])
    )
    @mock.patch("bilbyui.schema.request_file_download_ids", return_value=(False, "download error"))
    def test_generate_file_download_ids_failure(self, *_):
        self.query(RESULT_FILES_QUERY % self.global_id)
        token = str(FileDownloadToken.objects.get(job=self.job).token)
        response = self.query(DOWNLOAD_IDS_MUTATION, input_data={"jobId": self.global_id, "downloadTokens": [token]})
        self.assertIsNone(response.data["generateFileDownloadIds"])
        self.assertEqual(str(response.errors[0]["message"]), "download error")

    @silence_errors
    def test_upload_supporting_files_invalid_token(self):
        test_file = SimpleUploadedFile(name="t.txt", content=b"x", content_type="text/plain")
        response = self.file_query(
            "mutation($input: UploadSupportingFilesMutationInput!) { uploadSupportingFiles(input: $input) { result { result } } }",
            input_data={"supportingFiles": [{"fileToken": str(uuid.uuid4()), "supportingFile": None}]},
            files={"input.supportingFiles.0.supportingFile": test_file},
        )
        self.assertEqual(
            response.errors[0]["message"], "At least one supporting file upload token is invalid or expired."
        )

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_hdf5_job_upload_invalid_token(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        ini = create_test_ini_string({"label": "hdf5_job", "outdir": "./"}, True)
        response = self.file_query(
            "mutation($input: UploadHdf5BilbyJobMutationInput!) { uploadHdf5BilbyJob(input: $input) { result { jobId } } }",
            input_data={
                "uploadToken": str(uuid.uuid4()),
                "details": {"name": "hdf5_job", "description": "T", "private": False},
                "hdf5File": None,
                "iniFile": None,
            },
            files={
                "input.hdf5File": SimpleUploadedFile(
                    name="t.hdf5", content=b"x", content_type="application/octet-stream"
                ),
                "input.iniFile": SimpleUploadedFile(name="t.ini", content=ini.encode(), content_type="text/plain"),
            },
        )
        self.assertEqual(response.errors[0]["message"], "Job upload token is invalid or expired.")
