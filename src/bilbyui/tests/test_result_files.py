import uuid
from tempfile import TemporaryDirectory
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from graphql_relay import to_global_id

from bilbyui.constants import BilbyJobType
from bilbyui.models import FileDownloadToken, BilbyJob, ExternalBilbyJob
from bilbyui.tests.test_job_upload import get_upload_token
from bilbyui.tests.test_utils import silence_errors, create_test_upload_data, create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestResultFilesAndGenerateFileDownloadIdsNotUploaded(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        self.global_id = to_global_id("BilbyJobNode", self.job.id)

        self.files = [
            {"path": "/a", "isDir": True, "fileSize": "0"},
            {"path": "/a/path", "isDir": True, "fileSize": "0"},
            {"path": "/a/path/here2.txt", "isDir": False, "fileSize": "12345"},
            {"path": "/a/path/here3.txt", "isDir": False, "fileSize": "123456"},
            {"path": "/a/path/here4.txt", "isDir": False, "fileSize": "1234567"},
        ]

        self.query = f"""
            query {{
                bilbyResultFiles (jobId: "{self.global_id}") {{
                    files {{
                        path
                        isDir
                        fileSize
                        downloadToken
                    }}
                    jobType
                }}
            }}
            """

        self.mutation = """
                mutation ResultFileMutation($input: GenerateFileDownloadIdsInput!) {
                    generateFileDownloadIds(input: $input) {
                        result
                    }
                }
            """

    def request_file_list_mock(*args, **kwargs):
        return True, [
            {"path": "/a", "isDir": True, "fileSize": 0},
            {"path": "/a/path", "isDir": True, "fileSize": 0},
            {"path": "/a/path/here2.txt", "isDir": False, "fileSize": 12345},
            {"path": "/a/path/here3.txt", "isDir": False, "fileSize": 123456},
            {"path": "/a/path/here4.txt", "isDir": False, "fileSize": 1234567},
        ]

    def request_file_download_ids_mock(*args, **kwargs):
        return True, [uuid.uuid4() for _ in args[1]]

    @silence_errors
    @mock.patch("bilbyui.models.request_file_list", side_effect=request_file_list_mock)
    @mock.patch("bilbyui.schema.request_file_download_ids", side_effect=request_file_download_ids_mock)
    def test_not_uploaded_job(self, request_file_list, request_file_download_id_mock):
        # Iterate twice, first is unauthenticated user, second is authenticated user
        self.client.authenticate(None)
        for _ in range(2):
            # Clean up any file download tokens
            FileDownloadToken.objects.all().delete()

            response = self.client.execute(self.query)

            for i, f in enumerate(self.files):
                if f["isDir"]:
                    self.files[i]["downloadToken"] = None
                else:
                    self.files[i]["downloadToken"] = str(
                        FileDownloadToken.objects.get(job=self.job, path=f["path"]).token
                    )

            expected = {"bilbyResultFiles": {"files": self.files, "jobType": BilbyJobType.NORMAL}}
            self.assertDictEqual(response.data, expected)

            download_tokens = [f["downloadToken"] for f in filter(lambda x: not x["isDir"], self.files)]

            self.client.authenticate(self.user)

        self.client.authenticate(None)
        for _ in range(2):
            response = self.client.execute(
                self.mutation, {"input": {"jobId": self.global_id, "downloadTokens": [download_tokens[0]]}}
            )

            # Make sure the regex is parsable
            self.assertEqual(len(response.data["generateFileDownloadIds"]["result"]), 1)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][0], version=4)

            response = self.client.execute(
                self.mutation, {"input": {"jobId": self.global_id, "downloadTokens": download_tokens}}
            )

            # Make sure that the UUID's are parsable
            self.assertEqual(len(response.data["generateFileDownloadIds"]["result"]), 3)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][0], version=4)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][1], version=4)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][2], version=4)

            self.client.authenticate(self.user)

        # Expire one of the FileDownloadTokens
        tk = FileDownloadToken.objects.all()[1]
        tk.created = timezone.now() - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
        tk.save()

        response = self.client.execute(
            self.mutation, {"input": {"jobId": self.global_id, "downloadTokens": download_tokens}}
        )

        self.assertEqual(response.data["generateFileDownloadIds"], None)
        self.assertEqual(str(response.errors[0]), "At least one token was invalid or expired.")


@override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
class TestResultFilesAndGenerateFileDownloadIdsUploaded(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        # Create a new uploaded bilby job
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name, "detectors": "['H1']", "outdir": "./"}, True)

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(
            """
                mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
                  uploadBilbyJob(input: $input) {
                    result {
                      jobId
                    }
                  }
                }
            """,
            test_input,
        )

        self.global_id = response.data["uploadBilbyJob"]["result"]["jobId"]
        self.job = BilbyJob.objects.all().last()

        self.query = f"""
            query {{
                bilbyResultFiles (jobId: "{self.global_id}") {{
                    files {{
                        path
                        isDir
                        fileSize
                        downloadToken
                    }}
                    jobType
                }}
            }}
            """

        self.mutation = """
                mutation ResultFileMutation($input: GenerateFileDownloadIdsInput!) {
                    generateFileDownloadIds(input: $input) {
                        result
                    }
                }
            """

    @silence_errors
    def test_uploaded_job(self):
        self.job.job_type = BilbyJobType.UPLOADED
        self.job.save()

        # Iterate twice, first iteration is anonymous user, second is authenticated user
        self.client.authenticate(None)
        for _ in range(2):
            # Clean up any file download tokens
            FileDownloadToken.objects.all().delete()

            response = self.client.execute(self.query)

            files = response.data["bilbyResultFiles"]["files"]

            for i, f in enumerate(files):
                if f["isDir"]:
                    files[i]["downloadToken"] = None
                else:
                    files[i]["downloadToken"] = str(FileDownloadToken.objects.get(job=self.job, path=f["path"]).token)

            expected = {"bilbyResultFiles": {"files": files, "jobType": BilbyJobType.UPLOADED}}
            self.assertDictEqual(response.data, expected)

            download_tokens = [f["downloadToken"] for f in filter(lambda x: not x["isDir"], files)]

            self.client.authenticate(self.user)

        self.client.authenticate(None)
        for _ in range(2):
            response = self.client.execute(
                self.mutation, {"input": {"jobId": self.global_id, "downloadTokens": [download_tokens[0]]}}
            )

            # Make sure the result is the same as the download token
            self.assertEqual(len(response.data["generateFileDownloadIds"]["result"]), 1)
            self.assertEqual(response.data["generateFileDownloadIds"]["result"], [download_tokens[0]])

            response = self.client.execute(
                self.mutation, {"input": {"jobId": self.global_id, "downloadTokens": download_tokens}}
            )

            # Make sure that the result is the same as the download tokens
            self.assertEqual(response.data["generateFileDownloadIds"]["result"], download_tokens)

            self.client.authenticate(self.user)

        # Expire one of the FileDownloadTokens
        tk = FileDownloadToken.objects.all()[1]
        tk.created = timezone.now() - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
        tk.save()

        response = self.client.execute(
            self.mutation, {"input": {"jobId": self.global_id, "downloadTokens": download_tokens}}
        )

        self.assertEqual(response.data["generateFileDownloadIds"], None)
        self.assertEqual(str(response.errors[0]), "At least one token was invalid or expired.")


class TestExternalJobResultFiles(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            job_type=BilbyJobType.EXTERNAL,
        )

        self.external_job = ExternalBilbyJob.objects.create(job=self.job, url="https://www.example.com/test/file")

        self.global_id = to_global_id("BilbyJobNode", self.job.id)

        self.query = f"""
            query {{
                bilbyResultFiles (jobId: "{self.global_id}") {{
                    files {{
                        path
                        isDir
                        fileSize
                        downloadToken
                    }}
                    jobType
                }}
            }}
            """

    @silence_errors
    def test_uploaded_job(self):
        # Iterate twice, first iteration is anonymous user, second is authenticated user
        self.client.authenticate(None)
        for _ in range(2):
            response = self.client.execute(self.query)

            self.assertEqual(response.data["bilbyResultFiles"]["jobType"], BilbyJobType.EXTERNAL)
            self.assertEqual(len(response.data["bilbyResultFiles"]["files"]), 1)
            self.assertDictEqual(
                response.data["bilbyResultFiles"]["files"][0],
                {"path": self.external_job.url, "isDir": None, "fileSize": None, "downloadToken": None},
            )

            self.client.authenticate(self.user)
