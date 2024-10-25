import json
import os.path
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, IniKeyValue, SupportingFile
from bilbyui.tests.test_utils import create_test_ini_string, compare_ini_kvs, silence_errors, create_test_upload_data
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


def get_upload_token(client):
    generate_job_upload_token_mutation = """
        query GenerateBilbyJobUploadToken {
          generateBilbyJobUploadToken {
            token
          }
        }
    """

    response = client.execute(generate_job_upload_token_mutation)

    return response


class TestJobUpload(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="bill", first_name="bill", last_name="nye")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
              uploadBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_unauthorised_user(self):
        # Test user not logged in
        self.client.authenticate(None)

        response = get_upload_token(self.client)
        self.assertEqual(response.errors[0].message, "You do not have permission to perform this action")

        self.client.authenticate(self.user, is_ligo=True)

        test_name = "Test Name"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                "label": test_name,
            }
        )

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": str(uuid.uuid4()),
                "details": {"name": test_name, "description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertEqual(response.errors[0].message, "Job upload token is invalid or expired.")

        self.assertDictEqual({"uploadBilbyJob": None}, response.data)

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_success(self):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

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
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data)

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, test_ini_string)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)
        self.assertEqual(job.job_type, BilbyJobType.UPLOADED)

        # Check that the output directories and ini file were correctly created
        job_dir = job.get_upload_directory()
        self.assertTrue(os.path.isdir(job_dir))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "data")))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "result")))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "results_page")))
        self.assertTrue(os.path.isfile(os.path.join(job_dir, "myjob_config_complete.ini")))

        self.assertTrue(os.path.isfile(os.path.join(job_dir, "archive.tar.gz")))

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_success_outdir_replace(self):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_name = "another_job"
        test_description = "Another Description"
        test_private = True

        test_ini_string = create_test_ini_string({"label": test_name, "outdir": "/some/path/not/good/"}, True)

        test_file = SimpleUploadedFile(
            name="anothertest.tar.gz",
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

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data)

        job = BilbyJob.objects.all().last()
        self.assertTrue(IniKeyValue.objects.filter(job=job, key="outdir", value=json.dumps("./")).exists())

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)
        self.assertEqual(job.job_type, BilbyJobType.UPLOADED)

        # Check that the output directories and ini file were correctly created
        job_dir = job.get_upload_directory()
        self.assertTrue(os.path.isdir(job_dir))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "data")))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "result")))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "results_page")))
        self.assertTrue(os.path.isfile(os.path.join(job_dir, "another_job_config_complete.ini")))

        self.assertTrue(os.path.isfile(os.path.join(job_dir, "archive.tar.gz")))

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_missing_data(self):
        for missing_dir in ["data", "result", "results_page"]:
            token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

            test_name = missing_dir
            test_description = f"{missing_dir} Description"
            test_private = False

            test_ini_string = create_test_ini_string(
                {
                    "label": test_name,
                },
                True,
            )

            test_file = SimpleUploadedFile(
                name="test.tar.gz",
                content=create_test_upload_data(test_ini_string, test_name, **{f"include_{missing_dir}": False}),
                content_type="application/gzip",
            )

            test_input = {
                "input": {
                    "uploadToken": token,
                    "details": {"description": test_description, "private": test_private},
                    "jobFile": test_file,
                }
            }

            response = self.client.execute(self.mutation, test_input)

            self.assertEqual(
                f"Invalid directory structure, expected directory ./{missing_dir} to exist.", response.errors[0].message
            )

            self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_missing_ini(self):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_name = "missing_ini"
        test_description = "Missing Ini Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                "label": test_name,
            },
            True,
        )

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name, no_ini_file=True),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertEqual(
            "Invalid number of ini files ending in `_config_complete.ini`. There should be exactly one.",
            response.errors[0].message,
        )

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_many_ini(self):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_name = "missing_ini"
        test_description = "Missing Ini Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                "label": test_name,
            },
            True,
        )

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name, multiple_ini_files=True),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertEqual(
            "Invalid number of ini files ending in `_config_complete.ini`. There should be exactly one.",
            response.errors[0].message,
        )

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_invalid_tar_gz_name(self):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_name = "invalid_tar_gz_name"
        test_description = "Invalid .tar.gz Name Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                "label": test_name,
            },
            True,
        )

        test_file = SimpleUploadedFile(
            name="test.tar.g",
            content=create_test_upload_data(test_ini_string, test_name, no_ini_file=True),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertEqual("Job upload should be a tar.gz file", response.errors[0].message)

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_corrupt_tar_gz(self):
        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_description = "Corrupt .tar.gz Description"
        test_private = False

        test_file = SimpleUploadedFile(name="test.tar.gz", content=b"1234567abcdefg", content_type="application/gzip")

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": test_description, "private": test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertEqual("Invalid or corrupt tar.gz file", response.errors[0].message)

        self.assertFalse(BilbyJob.objects.all().exists())


class TestJobUploadLigoPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

        test_private = False

        self.mutation = """
            mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
              uploadBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

        self.params = {
            "input": {"details": {"description": "test_description", "private": test_private}, "jobFile": None}
        }

        self.expected_one = {"uploadBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.expected_none = {"uploadBilbyJob": None}

    @silence_errors
    def test_non_ligo_user_with_gwosc(self):
        # Test checks that a LIGO user does not create a LIGO job if the data is real and channels are GWOSC
        self.client.authenticate(self.user, is_ligo=False)

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]
        self.params["input"]["uploadToken"] = token

        ini_string = create_test_ini_string(
            config_dict={"label": "testjob", "n-simulation": 0, "channel-dict": {"H1": "GWOSC", "L1": "GWOSC"}},
            complete=True,
        )

        self.params["input"]["jobFile"] = SimpleUploadedFile(
            name="test.tar.gz", content=create_test_upload_data(ini_string, "testjob"), content_type="application/gzip"
        )

        response = self.client.execute(self.mutation, self.params)

        self.assertDictEqual(self.expected_one, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_gwosc(self):
        # This test checks that a non LIGO user can still create non LIGO jobs
        self.client.authenticate(self.user, is_ligo=True)

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]
        self.params["input"]["uploadToken"] = token

        ini_string = create_test_ini_string(
            config_dict={"label": "testjob", "n-simulation": 0, "channel-dict": {"H1": "GWOSC", "L1": "GWOSC"}},
            complete=True,
        )

        self.params["input"]["jobFile"] = SimpleUploadedFile(
            name="test.tar.gz", content=create_test_upload_data(ini_string, "testjob"), content_type="application/gzip"
        )

        response = self.client.execute(self.mutation, self.params)

        self.assertDictEqual(self.expected_one, response.data, "create bilbyJob mutation returned unexpected data.")

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_non_gwosc(self):
        # Test that LIGO users can make jobs with proprietary channels
        # Now if the channels are proprietary, the ligo user should be able to create jobs
        self.client.authenticate(self.user, is_ligo=True)

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]
        self.params["input"]["uploadToken"] = token

        for channel_dict in [
            {"H1": "GDS-CALIB_STRAIN", "L1": "GWOSC", "V1": "GWOSC"},
            {"H1": "GWOSC", "L1": "GDS-CALIB_STRAIN", "V1": "GWOSC"},
            {"H1": "GWOSC", "L1": "GWOSC", "V1": "Hrec_hoft_16384Hz"},
        ]:
            ini_string = create_test_ini_string(
                {"label": "testjob", "n-simulation": 0, "channel-dict": channel_dict}, complete=True
            )

            self.params["input"]["jobFile"] = SimpleUploadedFile(
                name="test.tar.gz",
                content=create_test_upload_data(ini_string, "testjob"),
                content_type="application/gzip",
            )

            response = self.client.execute(self.mutation, self.params)

            self.assertTrue("jobId" in response.data["uploadBilbyJob"]["result"])

            # Check that the job is marked as proprietary
            job = BilbyJob.objects.all().last()
            self.assertFalse(job.is_ligo_job)
            job.delete()


class TestJobUploadSupportingFiles(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="bill", first_name="bill", last_name="nye")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
              uploadBilbyJob(input: $input) {
                result {
                  jobId
                }
              }
            }
        """

        self.token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        self.test_name = "myjob"
        self.test_description = "Test Description"
        self.test_private = False

    def perform_upload(self, supporting_files, test_ini_string, ignored):
        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, self.test_name, supporting_files=supporting_files),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": self.token,
                "details": {"description": self.test_description, "private": self.test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadBilbyJob": {"result": {"jobId": "QmlsYnlKb2JOb2RlOjE="}}}

        self.assertDictEqual(expected, response.data)

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, test_ini_string, ignored=ignored)

        self.assertEqual(job.name, self.test_name)
        self.assertEqual(job.description, self.test_description)
        self.assertEqual(job.private, self.test_private)
        self.assertEqual(job.job_type, BilbyJobType.UPLOADED)

        # Check that the output directories and ini file were correctly created
        job_dir = job.get_upload_directory()
        self.assertTrue(os.path.isdir(job_dir))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "data")))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "result")))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, "results_page")))
        self.assertTrue(os.path.isfile(os.path.join(job_dir, "myjob_config_complete.ini")))

        self.assertTrue(os.path.isfile(os.path.join(job_dir, "archive.tar.gz")))

        return job, job_dir

    @silence_errors
    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_failure_file_not_exists(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat}"}, True
        )

        supporting_files = ["supporting_files/psd/V1-psd.dat1"]

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, self.test_name, supporting_files=supporting_files),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": self.token,
                "details": {"description": self.test_description, "private": self.test_private},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        expected = {"uploadBilbyJob": None}

        self.assertDictEqual(expected, response.data)

        self.assertEqual(BilbyJob.objects.count(), 0)
        self.assertEqual(SupportingFile.objects.count(), 0)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_psd1(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat}"}, True
        )

        supporting_files = ["supporting_files/psd/V1-psd.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["psd_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.PSD)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_psd2(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat, H1:./supporting_files/psd/H1-psd.dat}",
            },
            True,
        )

        supporting_files = ["supporting_files/psd/V1-psd.dat", "supporting_files/psd/H1-psd.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["psd_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.PSD)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_psd3(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat, H1:./psd/H1-psd.dat, L1:L1-psd.dat}",
            },
            True,
        )

        supporting_files = ["supporting_files/psd/V1-psd.dat", "psd/H1-psd.dat", "L1-psd.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["psd_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.PSD)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_calibration1(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat}",
            },
            True,
        )

        supporting_files = ["./supporting_files/calib/L1-calib.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["spline_calibration_envelope_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.CALIBRATION)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_calibration2(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat, "
                "V1:./supporting_files/calib/V1-calib.dat}",
            },
            True,
        )

        supporting_files = ["./supporting_files/calib/L1-calib.dat", "./supporting_files/calib/V1-calib.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["spline_calibration_envelope_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.CALIBRATION)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_calibration3(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat, "
                "V1:./supporting_files/calib/V1-calib.dat, "
                "H1:./supporting_files/calib/H1-calib.dat}",
            },
            True,
        )

        supporting_files = [
            "./supporting_files/calib/L1-calib.dat",
            "./supporting_files/calib/V1-calib.dat",
            "./supporting_files/calib/H1-calib.dat",
        ]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["spline_calibration_envelope_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.CALIBRATION)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_prior(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "prior-file": "./supporting_files/prior/myprior.prior"}, True
        )

        supporting_files = ["./supporting_files/prior/myprior.prior"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["prior_file"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.PRIOR)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_gps(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "gps-file": "./supporting_files/gps/gps.dat"}, True
        )

        supporting_files = ["./supporting_files/gps/gps.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["gps_file"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.GPS)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_timeslide(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "timeslide-file": "./supporting_files/timeslide/timeslide.dat"},
            True,
        )

        supporting_files = ["./supporting_files/timeslide/timeslide.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["timeslide_file"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.TIME_SLIDE)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_injection(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "injection-file": "./supporting_files/injection/injection.dat"},
            True,
        )

        supporting_files = ["./supporting_files/injection/injection.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["injection_file"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.INJECTION)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_numerical_relativity(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "numerical-relativity-file": "./supporting_files/nrf/nrf.dat"},
            True,
        )

        supporting_files = ["./supporting_files/nrf/nrf.dat"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["numerical_relativity_file"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.NUMERICAL_RELATIVITY)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_distance_marginalization(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "distance-marginalization-lookup-table": "./supporting_files/dml/dml.npz",
            },
            True,
        )

        supporting_files = ["./supporting_files/dml/dml.npz"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["distance_marginalization_lookup_table"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.DISTANCE_MARGINALIZATION_LOOKUP_TABLE)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_data_dict_1(self):
        test_ini_string = create_test_ini_string(
            {"label": self.test_name, "outdir": "./", "data-dict": "{H1: ./supporting_files/dat/h1.gwf}"}, True
        )

        supporting_files = ["./supporting_files/dat/h1.gwf"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["data_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.DATA)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_data_dict_2(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "data-dict": "{H1: ./supporting_files/dat/h1.gwf, L1: ./supporting_files/dat/l1.gwf}",
            },
            True,
        )

        supporting_files = ["./supporting_files/dat/h1.gwf", "./supporting_files/dat/l1.gwf"]

        job, job_dir = self.perform_upload(supporting_files, test_ini_string, ["data_dict"])

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())

            self.assertEqual(supporting_file.file_type, SupportingFile.DATA)

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_supporting_file_success_all(self):
        test_ini_string = create_test_ini_string(
            {
                "label": self.test_name,
                "outdir": "./",
                "psd-dict": "{L1:./supporting_files/psd/L1-psd.dat, V1:./supporting_files/psd/V1-psd.dat, "
                "H1:./supporting_files/psd/H1-psd.dat}",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat, "
                "V1:./supporting_files/calib/V1-calib.dat, "
                "H1:./supporting_files/calib/H1-calib.dat}",
                "prior-file": "./supporting_files/prior/myprior.prior",
                "gps-file": "./supporting_files/gps/gps.dat",
                "timeslide-file": "./supporting_files/timeslide/timeslide.dat",
                "injection-file": "./supporting_files/injection/injection.dat",
                "numerical-relativity-file": "./supporting_files/nrf/nrf.dat",
                "distance-marginalization-lookup-table": "./supporting_files/dml/dml.npz",
                "data-dict": "{H1: ./supporting_files/dat/h1.gwf, L1: ./supporting_files/dat/l1.gwf, "
                "V1: ./supporting_files/dat/v1.gwf}",
            },
            True,
        )

        supporting_files = [
            "./supporting_files/psd/L1-psd.dat",
            "./supporting_files/psd/V1-psd.dat",
            "./supporting_files/psd/H1-psd.dat",
            "./supporting_files/calib/L1-calib.dat",
            "./supporting_files/calib/V1-calib.dat",
            "./supporting_files/calib/H1-calib.dat",
            "./supporting_files/prior/myprior.prior",
            "./supporting_files/gps/gps.dat",
            "./supporting_files/timeslide/timeslide.dat",
            "./supporting_files/injection/injection.dat",
            "./supporting_files/nrf/nrf.dat",
            "./supporting_files/dml/dml.npz",
            "./supporting_files/dat/h1.gwf",
            "./supporting_files/dat/l1.gwf",
            "./supporting_files/dat/v1.gwf",
        ]

        job, job_dir = self.perform_upload(
            supporting_files,
            test_ini_string,
            [
                "psd_dict",
                "spline_calibration_envelope_dict",
                "prior_file",
                "gps_file",
                "timeslide_file",
                "injection_file",
                "numerical_relativity_file",
                "distance_marginalization_lookup_table",
                "data_dict",
            ],
        )

        # There should be a supporting file record for each supporting file
        self.assertEqual(job.supportingfile_set.filter(upload_token__isnull=True).count(), len(supporting_files))

        # File should exist in the unpacked archive
        for supporting_file in supporting_files:
            self.assertTrue((Path(job_dir) / supporting_file).is_file())

        # File should exist in the supporting files for this job
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        for supporting_file in job.supportingfile_set.all():
            self.assertTrue((job_dir / str(supporting_file.id)).is_file())


class TestJobUploadNameValidation(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)

        self.mutation = """
                mutation JobUploadMutation($input: UploadBilbyJobMutationInput!) {
                  uploadBilbyJob(input: $input) {
                    result {
                      jobId
                    }
                  }
                }
            """

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_invalid_job_name_symbols(self):
        test_name = "Test_Name$"

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_ini_string = create_test_ini_string({"label": test_name, "outdir": "./"}, True)

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": "a description", "private": True},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertDictEqual({"uploadBilbyJob": None}, response.data)

        self.assertEqual(response.errors[0].message, "Job name must not contain any spaces or special characters.")

    @silence_errors
    def test_invalid_job_name_too_long(self):
        test_name = "a" * 500

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_ini_string = create_test_ini_string({"label": test_name, "outdir": "./"}, True)

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": "a description", "private": True},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertDictEqual({"uploadBilbyJob": None}, response.data)

        self.assertEqual(response.errors[0].message, "Job name must be less than 255 characters long.")
    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_invalid_job_name_too_short(self):
        test_name = "a"

        token = get_upload_token(self.client).data["generateBilbyJobUploadToken"]["token"]

        test_ini_string = create_test_ini_string({"label": test_name, "outdir": "./"}, True)

        test_file = SimpleUploadedFile(
            name="test.tar.gz",
            content=create_test_upload_data(test_ini_string, test_name),
            content_type="application/gzip",
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {"description": "a description", "private": True},
                "jobFile": test_file,
            }
        }

        response = self.client.execute(self.mutation, test_input)

        self.assertDictEqual({"uploadBilbyJob": None}, response.data)

        self.assertEqual(response.errors[0].message, "Job name must be at least 5 characters long.")
