import os
import uuid
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import (
    silence_errors,
    create_test_upload_data,
    create_test_ini_string,
    get_file_download_tokens,
    get_files,
)
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
class TestUploadedJobFileDownload(BilbyTestCase):
    def setUp(self):
        self.authenticate()

        token = self.get_upload_token()

        # Create a new uploaded bilby job
        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string({"label": test_name, "outdir": "./"}, True)

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

        self.mut_input = {"jobId": self.global_id, "downloadTokens": None}

        self.http_client = Client()

    def generate_file_download_tokens(self):
        response = self.query(self.query_string)
        download_tokens = get_file_download_tokens(response)
        return download_tokens, response

    def generate_download_id_from_token(self, token):
        self.mut_input["downloadTokens"] = [token]

        response = self.query(self.mutation_string, input_data=self.mut_input)

        return response.data["generateFileDownloadIds"]["result"][0]

    @silence_errors
    def test_no_token(self):
        response = self.http_client.get(f"{reverse(viewname='file_download')}")
        self.assertEqual(response.status_code, 404)

    @silence_errors
    def test_invalid_token(self):
        download_tokens, _ = self.generate_file_download_tokens()

        self.mut_input["downloadTokens"] = [download_tokens[0]]

        response = self.query(self.mutation_string, input_data=self.mut_input)

        token = response.data["generateFileDownloadIds"]["result"][0]
        token = token + "_not_real"

        response = self.http_client.get(f"{reverse(viewname='file_download')}?fileId={token}")
        self.assertEqual(response.status_code, 404)

        response = self.http_client.get(f"{reverse(viewname='file_download')}?fileId={uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)

    @silence_errors
    def test_success_no_force_download(self):
        download_tokens, response = self.generate_file_download_tokens()
        files = get_files(response)

        for idx in range(len(files)):
            token = self.generate_download_id_from_token(download_tokens[idx])

            response = self.http_client.get(f"{reverse(viewname='file_download')}?fileId={token}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
            self.assertEqual(
                response.headers["Content-Disposition"],
                f'inline; filename="{os.path.basename(files[idx]["path"][1:])}"',
            )

            content = b"".join(list(response))

            with open(
                os.path.join(self.job.get_upload_directory(), files[idx]["path"][1:]),
                "rb",
            ) as f:
                self.assertEqual(content, f.read())

    @silence_errors
    def test_success_force_download(self):
        download_tokens, response = self.generate_file_download_tokens()
        files = get_files(response)

        for idx in range(len(files)):
            token = self.generate_download_id_from_token(download_tokens[idx])

            response = self.http_client.get(f"{reverse(viewname='file_download')}?fileId={token}&forceDownload")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
            self.assertEqual(
                response.headers["Content-Disposition"],
                f'attachment; filename="{os.path.basename(files[idx]["path"][1:])}"',
            )

            content = b"".join(list(response))

            with open(
                os.path.join(self.job.get_upload_directory(), files[idx]["path"][1:]),
                "rb",
            ) as f:
                self.assertEqual(content, f.read())
