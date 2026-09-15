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
from bilbyui.models import BilbyJob, ExternalBilbyJob, FileDownloadToken
from bilbyui.tests.test_utils import (
    create_test_ini_string,
    create_test_upload_data,
    silence_errors,
)
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestResultFilesAndGenerateFileDownloadIdsNotUploaded(BilbyTestCase):
    def setUp(self):
        self.authenticate()

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

        self.query_string = f"""
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

        self.mutation_string = """
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
    @mock.patch(
        "bilbyui.schema.request_file_download_ids",
        side_effect=request_file_download_ids_mock,
    )
    def test_not_uploaded_job(self, request_file_list, request_file_download_id_mock):
        # Iterate twice, first is unauthenticated user, second is authenticated user
        self.deauthenticate()
        for _ in range(2):
            # Clean up any file download tokens
            FileDownloadToken.objects.all().delete()

            response = self.query(self.query_string)

            for i, f in enumerate(self.files):
                if f["isDir"]:
                    self.files[i]["downloadToken"] = None
                else:
                    self.files[i]["downloadToken"] = str(
                        FileDownloadToken.objects.get(job=self.job, path=f["path"]).token
                    )

            expected = {
                "bilbyResultFiles": {
                    "files": self.files,
                    "jobType": BilbyJobType.NORMAL,
                }
            }
            self.assertDictEqual(response.data, expected)

            download_tokens = [f["downloadToken"] for f in self.files if not f["isDir"]]

            self.authenticate()

        self.deauthenticate()
        for _ in range(2):
            response = self.query(
                self.mutation_string,
                input_data={
                    "jobId": self.global_id,
                    "downloadTokens": [download_tokens[0]],
                },
            )

            # Make sure the regex is parsable
            self.assertEqual(len(response.data["generateFileDownloadIds"]["result"]), 1)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][0], version=4)

            response = self.query(
                self.mutation_string,
                input_data={"jobId": self.global_id, "downloadTokens": download_tokens},
            )

            # Make sure that the UUID's are parsable
            self.assertEqual(len(response.data["generateFileDownloadIds"]["result"]), 3)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][0], version=4)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][1], version=4)
            uuid.UUID(response.data["generateFileDownloadIds"]["result"][2], version=4)

            self.authenticate()

        # Expire one of the FileDownloadTokens
        tk = FileDownloadToken.objects.all()[1]
        tk.created = timezone.now() - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
        tk.save()

        response = self.query(
            self.mutation_string,
            input_data={"jobId": self.global_id, "downloadTokens": download_tokens},
        )

        self.assertIsNone(response.data["generateFileDownloadIds"])
        self.assertEqual(
            str(response.errors[0]["message"]),
            "At least one token was invalid or expired.",
        )

    @silence_errors
    @mock.patch(
        "bilbyui.models.request_file_list",
        return_value=(
            True,
            [
                {"path": "/bad.txt", "isDir": False, "fileSize": "not-a-number"},
                {"path": "/null.txt", "isDir": False, "fileSize": None},
                {"path": "/list.txt", "isDir": False, "fileSize": [1, 2]},
            ],
        ),
    )
    def test_malformed_file_size(self, *_):
        response = self.query(self.query_string)
        self.assertIsNone(response.errors)
        files = response.data["bilbyResultFiles"]["files"]
        self.assertEqual([f["fileSize"] for f in files], [None, None, None])


@override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
class TestResultFilesAndGenerateFileDownloadIdsUploaded(BilbyTestCase):
    def setUp(self):
        self.authenticate()

        token = self.get_upload_token()  # Create a new uploaded bilby job

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
            "uploadToken": token,
            "details": {"description": test_description, "private": test_private},
            "jobFile": None,
        }
        test_files = {"input.jobFile": test_file}

        response = self.file_query(
            """
                mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
                  uploadBilbyJob(input: $input) {
                    result {
                      jobId
                    }
                  }
                }
            """,
            input_data=test_input,
            files=test_files,
        )

        self.global_id = response.data["uploadBilbyJob"]["result"]["jobId"]
        self.job = BilbyJob.objects.all().last()

        self.query_string = f"""
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

        self.mutation_string = """
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
        self.deauthenticate()
        for _ in range(2):
            # Clean up any file download tokens
            FileDownloadToken.objects.all().delete()

            response = self.query(self.query_string)

            files = response.data["bilbyResultFiles"]["files"]

            for i, f in enumerate(files):
                if f["isDir"]:
                    files[i]["downloadToken"] = None
                else:
                    files[i]["downloadToken"] = str(FileDownloadToken.objects.get(job=self.job, path=f["path"]).token)

            expected = {"bilbyResultFiles": {"files": files, "jobType": BilbyJobType.UPLOADED}}
            self.assertDictEqual(response.data, expected)

            download_tokens = [f["downloadToken"] for f in files if not f["isDir"]]

            self.authenticate()

        self.deauthenticate()
        for _ in range(2):
            response = self.query(
                self.mutation_string,
                input_data={
                    "jobId": self.global_id,
                    "downloadTokens": [download_tokens[0]],
                },
            )

            # Make sure the result is the same as the download token
            self.assertEqual(len(response.data["generateFileDownloadIds"]["result"]), 1)
            self.assertEqual(response.data["generateFileDownloadIds"]["result"], [download_tokens[0]])

            response = self.query(
                self.mutation_string,
                input_data={"jobId": self.global_id, "downloadTokens": download_tokens},
            )

            # Make sure that the result is the same as the download tokens
            self.assertEqual(response.data["generateFileDownloadIds"]["result"], download_tokens)

            self.authenticate()

        # Expire one of the FileDownloadTokens
        tk = FileDownloadToken.objects.all()[1]
        tk.created = timezone.now() - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
        tk.save()

        response = self.query(
            self.mutation_string,
            input_data={"jobId": self.global_id, "downloadTokens": download_tokens},
        )

        self.assertIsNone(response.data["generateFileDownloadIds"])
        self.assertEqual(
            str(response.errors[0]["message"]),
            "At least one token was invalid or expired.",
        )


class TestExternalJobResultFiles(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()
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

        self.query_string = f"""
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
        self.deauthenticate()
        for _ in range(2):
            response = self.query(self.query_string)

            self.assertEqual(response.data["bilbyResultFiles"]["jobType"], BilbyJobType.EXTERNAL)
            self.assertEqual(len(response.data["bilbyResultFiles"]["files"]), 1)
            self.assertDictEqual(
                response.data["bilbyResultFiles"]["files"][0],
                {
                    "path": self.external_job.url,
                    "isDir": False,
                    "fileSize": None,
                    "downloadToken": None,
                },
            )

            self.authenticate()


class TestResultFilesMalformedJobId(BilbyTestCase):
    def setUp(self):
        self.authenticate()

    @silence_errors
    @mock.patch("bilbyui.schema.from_global_id", side_effect=ValueError("malformed global id"))
    def test_malformed_job_id_returns_none(self, _mock_from_global_id):
        response = self.query(
            """
            query {
                bilbyResultFiles (jobId: "not-a-valid-global-id") {
                    files {
                        path
                    }
                    jobType
                }
            }
            """
        )

        self.assertIsNone(response.data["bilbyResultFiles"])
        self.assertIsNone(response.errors)


class TestGenerateFileDownloadIdsMalformedJobId(BilbyTestCase):
    def setUp(self):
        self.authenticate()

    @silence_errors
    def test_malformed_job_id_returns_clean_error(self):
        response = self.query(
            """
            mutation ResultFileMutation($input: GenerateFileDownloadIdsInput!) {
                generateFileDownloadIds(input: $input) {
                    result
                }
            }
            """,
            input_data={"jobId": "not-a-valid-id", "downloadTokens": ["some-token"]},
        )

        self.assertIsNone(response.data["generateFileDownloadIds"])
        self.assertEqual(response.errors[0]["message"], "Invalid job_id")

    @silence_errors
    def test_malformed_job_id_returns_clean_error_anonymous(self):
        self.deauthenticate()

        response = self.query(
            """
            mutation ResultFileMutation($input: GenerateFileDownloadIdsInput!) {
                generateFileDownloadIds(input: $input) {
                    result
                }
            }
            """,
            input_data={"jobId": "not-a-valid-id", "downloadTokens": ["some-token"]},
        )

        self.assertIsNone(response.data["generateFileDownloadIds"])
        self.assertEqual(response.errors[0]["message"], "Invalid job_id")


class TestResultFileTemplates(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="result-template-job",
            description="result template coverage",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def render_results(self, files, job=None):
        from django.template.loader import render_to_string

        return render_to_string(
            "bilbyui/_results.html",
            {"files": files, "job": job or self.job},
        )

    def test_result_table_and_file_rows_are_accessible(self):
        files = [
            {
                "path": "/very/long/result/directory/posterior.hdf5",
                "is_dir": False,
                "file_size": 1024,
                "download_token": "first-token",
            },
            {
                "path": "/very/long/result/directory/samples.json",
                "is_dir": False,
                "file_size": None,
                "download_token": "second-token",
            },
            {
                "path": "/very/long/result/directory/subdirectory",
                "is_dir": True,
                "file_size": 0,
                "download_token": None,
            },
        ]

        html = self.render_results(files)

        self.assertIn('class="results-table-wrap"', html)
        self.assertIn('role="region"', html)
        self.assertIn('tabindex="0"', html)
        self.assertIn('aria-label="Result files table"', html)
        self.assertIn("<caption", html)
        self.assertIn("Result files for this Bilby job", html)
        self.assertIn('<th scope="col">File</th>', html)
        self.assertIn('<th scope="col">Type</th>', html)
        self.assertIn('<th scope="col">File size</th>', html)
        self.assertIn(">posterior.hdf5</a>", html)
        self.assertIn(">samples.json</a>", html)
        self.assertIn(">subdirectory</span>", html)
        self.assertEqual(html.count('class="tech-value-copy"'), 3)
        self.assertEqual(html.count('class="tech-value-toggle"'), 3)
        self.assertEqual(html.count('aria-expanded="false"'), 3)
        self.assertEqual(html.count('aria-controls="result-file-path-'), 3)
        self.assertIn('aria-controls="result-file-path-1"', html)
        self.assertIn('aria-controls="result-file-path-2"', html)
        self.assertIn('aria-controls="result-file-path-3"', html)
        self.assertEqual(html.count('rel="noopener noreferrer"'), 2)
        self.assertIn("Copy path", html)
        self.assertIn("Directory", html)
        self.assertIn("—", html)

    def test_external_file_uses_basename_link_and_secure_external_attributes(self):
        external_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="external-result-template-job",
            description="external result template coverage",
            private=False,
            job_type=BilbyJobType.EXTERNAL,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        url = "https://example.com/results/final-result.json?download=1&amp;source=test"

        html = self.render_results(
            [
                {
                    "path": url,
                    "is_dir": False,
                    "file_size": None,
                    "download_token": None,
                    "link_url": url,
                }
            ],
            job=external_job,
        )

        self.assertIn(">final-result.json?download=1&amp;amp;source=test</a>", html)
        self.assertIn('target="_blank" rel="noopener noreferrer"', html)
        self.assertIn("https://example.com/results/", html)
        self.assertEqual(html.count('class="tech-value-copy"'), 1)
        self.assertEqual(html.count('class="tech-value-toggle"'), 1)

        unsafe_url = "javascript:alert(1)"
        unsafe_html = self.render_results(
            [
                {
                    "path": unsafe_url,
                    "is_dir": False,
                    "file_size": None,
                    "download_token": None,
                    "link_url": "",
                }
            ],
            job=external_job,
        )
        self.assertNotIn('href="javascript:', unsafe_html)
        self.assertIn(unsafe_url, unsafe_html)

    def test_hostile_path_is_escaped_and_never_used_for_disclosure_id(self):
        hostile_path = '/results/<script>alert("x")</script>/"><img src=x onerror=alert(1)>.json'

        html = self.render_results(
            [
                {
                    "path": hostile_path,
                    "is_dir": True,
                    "file_size": None,
                    "download_token": None,
                }
            ]
        )

        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        self.assertIn('aria-controls="result-file-path-1"', html)
        self.assertNotIn('aria-controls="/results/', html)
        self.assertNotIn('id="/results/', html)

    def test_non_downloadable_file_and_directory_are_not_links(self):
        html = self.render_results(
            [
                {
                    "path": "/results/unavailable.dat",
                    "is_dir": False,
                    "file_size": None,
                    "download_token": None,
                },
                {
                    "path": "/results/archive",
                    "is_dir": True,
                    "file_size": 0,
                    "download_token": None,
                },
            ]
        )

        self.assertIn('<span class="tech-value-label">unavailable.dat</span>', html)
        self.assertIn('<span class="tech-value-label">archive</span>', html)
        self.assertNotIn("<a ", html)

    def test_empty_results_have_stable_message(self):
        html = self.render_results([])

        self.assertIn('<td colspan="3" class="text-muted">No result files found.</td>', html)
