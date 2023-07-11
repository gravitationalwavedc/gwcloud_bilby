import secrets
import shutil
import string
import uuid
from pathlib import Path
from unittest.mock import patch
from math import ceil

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from bilbyui.models import BilbyJob, SupportingFile
from bilbyui.tests.test_utils import compare_ini_kvs, create_test_ini_string, silence_errors
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestIniJobSubmission(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user, is_ligo=True)

        self.mutation = """
            mutation NewIniJobMutation($input: BilbyJobFromIniStringMutationInput!) {
              newBilbyJobFromIniString(input: $input) {
                result {
                  jobId
                  supportingFiles {
                    filePath
                    token
                  }
                }
              }
            }
        """

        self.supporting_file_mutation = """
            mutation SupportingFileUploadMutation($input: UploadSupportingFilesMutationInput!) {
              uploadSupportingFiles(input: $input) {
                result {
                  result
                }
              }
            }
        """

        self.test_name = "Test_Name"
        self.test_description = "Test Description"
        self.test_private = False

        self.test_input = {
            "input": {
                "params": {
                    "details": {
                        "name": self.test_name,
                        "description": self.test_description,
                        "private": self.test_private,
                    },
                    "iniString": {"iniString": None},
                }
            }
        }

        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.client.authenticate(self.user, is_ligo=True)

        self.http_client = Client()

    @patch("bilbyui.models.submit_job")
    def mock_ini_job_submission_with_supporting_files(self, test_ini_string, file_names, config_names, mock_api_call):
        """
        This function is called by subsequent tests and performs the bulk of the actual testing and asserting. It's
        main flow is basically the following:
        * Submit the provided ini file to create a new bilby job
        * Verify that the created job details are correct
        * Supporting files should be created and returned from the new bilby job call
        * Verify that the supporting file records were correctly created and returned
        * Check that the ini details were correctly saved in the database
        * Upload each supporting file and verify that it was created on disk
        * Verify that the job is not submitted until the last supporting file is uploaded, then the job should be
          submitted
        """

        self.test_input["input"]["params"]["iniString"]["iniString"] = test_ini_string

        mock_api_call.return_value = {"jobId": 4321}

        response = self.client.execute(self.mutation, self.test_input)

        job = BilbyJob.objects.all().last()

        # Test that the correct SupportingFile objects were created
        supporting_files = SupportingFile.objects.filter(job=job)
        self.assertEqual(supporting_files.count(), len(file_names))

        expected_supporting_files = []

        for v in file_names:
            sf = supporting_files.filter(key=v[0], file_name=Path(v[1]).name, file_type=v[2])
            self.assertTrue(sf.exists())
            expected_supporting_files.append({"filePath": v[1], "token": str(sf.first().upload_token)}),

        expected = {
            "newBilbyJobFromIniString": {
                "result": {"jobId": "QmlsYnlKb2JOb2RlOjE=", "supportingFiles": expected_supporting_files}
            }
        }

        response.data["newBilbyJobFromIniString"]["result"]["supportingFiles"].sort(key=lambda x: x["token"])
        expected["newBilbyJobFromIniString"]["result"]["supportingFiles"].sort(key=lambda x: x["token"])

        self.assertDictEqual(expected, response.data, "create bilbyJob mutation returned unexpected data.")

        # And should create all k/v's with default values
        compare_ini_kvs(self, job, test_ini_string, config_names)

        self.assertEqual(job.name, self.test_name)
        self.assertEqual(job.description, self.test_description)
        self.assertEqual(job.private, self.test_private)

        # If there are no supporting files, then the job should have been submitted
        if not supporting_files.count():
            self.assertEqual(job.job_controller_id, 4321)
            return

        # Job should not have been submitted as there is a supporting file
        self.assertIsNone(job.job_controller_id)

        # Now all files, checking that the job is only submitted once the last file upload has completed.
        def upload_supporting_files(tokens):
            content = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(128))

            file_input = {
                "input": {
                    "supportingFiles": [
                        {
                            "fileToken": token,
                            "supportingFile": SimpleUploadedFile(name="test.tar.gz", content=content.encode("utf-8")),
                        }
                        for token in tokens
                    ]
                }
            }

            response = self.client.execute(self.supporting_file_mutation, file_input)

            self.assertTrue(response.data["uploadSupportingFiles"]["result"]["result"])

        job.refresh_from_db()
        self.assertIsNone(job.job_controller_id)

        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        if job_dir.is_dir():
            shutil.rmtree(job_dir)

        # Breaks the supporting file list in half and uses the halves as batches to upload.
        # This makes sure that we can handle uploading lists of files, as well as not uploading all files at once.
        batch_size = ceil(len(supporting_files) / 2)
        for i in range(0, len(supporting_files), batch_size):
            job.refresh_from_db()
            self.assertIsNone(job.job_controller_id)

            supporting_files_subset = supporting_files[i: i + batch_size]
            upload_tokens = [sf.upload_token for sf in supporting_files_subset]
            upload_supporting_files(upload_tokens)

            for sf in supporting_files_subset:
                self.assertTrue((Path(job_dir) / str(sf.id)).is_file())

        job.refresh_from_db()
        self.assertEqual(job.job_controller_id, 4321)

    def test_ini_job_submission_supporting_file_psd1(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat}"},
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string, [["V1", "./supporting_files/psd/V1-psd.dat", SupportingFile.PSD]], "psd_dict"
        )

    def test_ini_job_submission_supporting_file_psd2(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "psd-dict": "{L1:./supporting_files/psd/L1-psd.dat, V1:./supporting_files/psd/V1-psd.dat}",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [
                ["L1", "./supporting_files/psd/L1-psd.dat", SupportingFile.PSD],
                ["V1", "./supporting_files/psd/V1-psd.dat", SupportingFile.PSD],
            ],
            "psd_dict",
        )

    def test_ini_job_submission_supporting_file_psd3(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "psd-dict": "{L1:./supporting_files/psd/L1-psd.dat, V1:./supporting_files/psd/V1-psd.dat, "
                "H1:./supporting_files/psd/H1-psd.dat}",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [
                ["L1", "./supporting_files/psd/L1-psd.dat", SupportingFile.PSD],
                ["V1", "./supporting_files/psd/V1-psd.dat", SupportingFile.PSD],
                ["H1", "./supporting_files/psd/H1-psd.dat", SupportingFile.PSD],
            ],
            "psd_dict",
        )

    def test_ini_job_submission_supporting_file_calibration1(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat}",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [["L1", "./supporting_files/calib/L1-calib.dat", SupportingFile.CALIBRATION]],
            "spline_calibration_envelope_dict",
        )

    def test_ini_job_submission_supporting_file_calibration2(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat, "
                "V1:./supporting_files/calib/V1-calib.dat}",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [
                ["L1", "./supporting_files/calib/L1-calib.dat", SupportingFile.CALIBRATION],
                ["V1", "./supporting_files/calib/V1-calib.dat", SupportingFile.CALIBRATION],
            ],
            "spline_calibration_envelope_dict",
        )

    def test_ini_job_submission_supporting_file_calibration3(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "spline-calibration-envelope-dict": "{L1:./supporting_files/calib/L1-calib.dat, "
                "V1:./supporting_files/calib/V1-calib.dat, "
                "H1:./supporting_files/calib/H1-calib.dat}",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [
                ["L1", "./supporting_files/calib/L1-calib.dat", SupportingFile.CALIBRATION],
                ["V1", "./supporting_files/calib/V1-calib.dat", SupportingFile.CALIBRATION],
                ["H1", "./supporting_files/calib/H1-calib.dat", SupportingFile.CALIBRATION],
            ],
            "spline_calibration_envelope_dict",
        )

    def test_ini_job_submission_supporting_file_prior(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "prior-file": "./supporting_files/prior/myprior.prior"}
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string, [[None, "./supporting_files/prior/myprior.prior", SupportingFile.PRIOR]], "prior_file"
        )

    def test_ini_job_submission_supporting_file_gps(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "gps-file": "./supporting_files/gps/gps.dat"}
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string, [[None, "./supporting_files/gps/gps.dat", SupportingFile.GPS]], "gps_file"
        )

    def test_ini_job_submission_supporting_file_timeslide(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "timeslide-file": "./supporting_files/timeslide/timeslide.dat",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [[None, "./supporting_files/timeslide/timeslide.dat", SupportingFile.TIME_SLIDE]],
            "timeslide_file",
        )

    def test_ini_job_submission_supporting_file_injection(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "injection-file": "./supporting_files/injection/injection.dat",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [[None, "./supporting_files/injection/injection.dat", SupportingFile.INJECTION]],
            "injection_file",
        )

    def test_ini_job_submission_supporting_file_numerical_relativity_file(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "numerical-relativity-file": "./supporting_files/nrf/nrf.dat"}
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [[None, "./supporting_files/nrf/nrf.dat", SupportingFile.NUMERICAL_RELATIVITY]],
            "numerical_relativity_file",
        )

    def test_ini_job_submission_supporting_file_distance_marginalization_lookup_table(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "distance-marginalization-lookup-table": "./supporting_files/dml/dml.npz",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [[None, "./supporting_files/dml/dml.npz", SupportingFile.DISTANCE_MARGINALIZATION_LOOKUP_TABLE]],
            "distance_marginalization_lookup_table",
        )

    def test_ini_job_submission_supporting_file_distance_marginalization_lookup_table_none(self):
        # If the DML is set to None, the client shouldn't be made to try to find
        # `.4s_distance_marginalization_lookup_phase.npz`
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
                "prior-file": "4s",
                "distance-marginalization-lookup-table": None,
            }
        )

        self.mock_ini_job_submission_with_supporting_files(test_ini_string, [], "distance_marginalization_lookup_table")

    def test_ini_job_submission_supporting_file_data_dict_1(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "data-dict": "{H1: ./supporting_files/dat/h1.gwf}"}
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string, [["H1", "./supporting_files/dat/h1.gwf", SupportingFile.DATA]], "data_dict"
        )

    def test_ini_job_submission_supporting_file_data_dict_2(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1', 'L1']",
                "data-dict": "{H1: ./supporting_files/dat/h1.gwf, L1: ./supporting_files/dat/l1.gwf}",
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [
                ["H1", "./supporting_files/dat/h1.gwf", SupportingFile.DATA],
                ["L1", "./supporting_files/dat/l1.gwf", SupportingFile.DATA],
            ],
            "data_dict",
        )

    def test_ini_job_submission_supporting_file_all(self):
        test_ini_string = create_test_ini_string(
            {
                "label": "Test_Name",
                "detectors": "['H1']",
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
            }
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string,
            [
                ["L1", "./supporting_files/psd/L1-psd.dat", SupportingFile.PSD],
                ["V1", "./supporting_files/psd/V1-psd.dat", SupportingFile.PSD],
                ["H1", "./supporting_files/psd/H1-psd.dat", SupportingFile.PSD],
                ["L1", "./supporting_files/calib/L1-calib.dat", SupportingFile.CALIBRATION],
                ["V1", "./supporting_files/calib/V1-calib.dat", SupportingFile.CALIBRATION],
                ["H1", "./supporting_files/calib/H1-calib.dat", SupportingFile.CALIBRATION],
                [None, "./supporting_files/prior/myprior.prior", SupportingFile.PRIOR],
                [None, "./supporting_files/gps/gps.dat", SupportingFile.GPS],
                [None, "./supporting_files/timeslide/timeslide.dat", SupportingFile.TIME_SLIDE],
                [None, "./supporting_files/injection/injection.dat", SupportingFile.INJECTION],
                [None, "./supporting_files/nrf/nrf.dat", SupportingFile.NUMERICAL_RELATIVITY],
                [None, "./supporting_files/dml/dml.npz", SupportingFile.DISTANCE_MARGINALIZATION_LOOKUP_TABLE],
                ["H1", "./supporting_files/dat/h1.gwf", SupportingFile.DATA],
                ["L1", "./supporting_files/dat/l1.gwf", SupportingFile.DATA],
                ["V1", "./supporting_files/dat/v1.gwf", SupportingFile.DATA],
            ],
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

    @silence_errors
    def test_download_supporting_files_invalid_token(self):
        # Test that using an invalid token raises an error
        response = self.http_client.get(f'{reverse(viewname="file_download")}?fileId={str(uuid.uuid4())}')
        self.assertEqual(response.status_code, 404)

    def test_download_supporting_files_valid_token_force_download(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat}"},
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string, [["V1", "./supporting_files/psd/V1-psd.dat", SupportingFile.PSD]], "psd_dict"
        )

        supporting_file = SupportingFile.objects.last()

        response = self.http_client.get(
            f'{reverse(viewname="file_download")}?fileId={supporting_file.download_token}&forceDownload'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="V1-psd.dat"')

        content = b"".join(list(response))

        # Get the supporting file path
        file_path = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(supporting_file.job.id) / str(supporting_file.id)

        with open(str(file_path), "rb") as f:
            self.assertEqual(content, f.read())

    def test_download_supporting_files_valid_token(self):
        test_ini_string = create_test_ini_string(
            {"label": "Test_Name", "detectors": "['H1']", "psd-dict": "{V1:./supporting_files/psd/V1-psd.dat}"},
        )

        self.mock_ini_job_submission_with_supporting_files(
            test_ini_string, [["V1", "./supporting_files/psd/V1-psd.dat", SupportingFile.PSD]], "psd_dict"
        )

        supporting_file = SupportingFile.objects.last()

        response = self.http_client.get(f'{reverse(viewname="file_download")}?fileId={supporting_file.download_token}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(response.headers["Content-Disposition"], 'inline; filename="V1-psd.dat"')

        content = b"".join(list(response))

        # Get the supporting file path
        file_path = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(supporting_file.job.id) / str(supporting_file.id)

        with open(str(file_path), "rb") as f:
            self.assertEqual(content, f.read())
