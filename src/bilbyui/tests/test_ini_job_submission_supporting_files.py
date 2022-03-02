import json
import os
import secrets
import shutil
import string
from pathlib import Path
from unittest.mock import patch

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import override_settings

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
            mutation SupportingFileUploadMutation($input: UploadSupportingFileMutationInput!) {
              uploadSupportingFile(input: $input) {
                result {
                  result
                }
              }
            }
        """

        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

    @patch("bilbyui.models.submit_job")
    def run_test_ini_job_submission_supporting_files(self, test_ini_string, file_names, config_names, mock_api_call):
        self.client.authenticate(self.user, is_ligo=True)

        mock_api_call.return_value = {'jobId': 4321}
        test_name = "Test Name"
        test_description = "Test Description"
        test_private = False

        test_input = {
            "input": {
                "params": {
                    "details": {
                        "name": test_name,
                        "description": test_description,
                        "private": test_private
                    },
                    "iniString": {
                        "iniString": test_ini_string
                    }
                }
            }
        }

        response = self.client.execute(self.mutation, test_input)

        job = BilbyJob.objects.all().last()

        # Test that the correct SupportingFile objects were created
        supporting_files = SupportingFile.objects.filter(job=job)
        self.assertEqual(supporting_files.count(), len(file_names))

        expected_supporting_files = []

        for v in file_names:
            sf = supporting_files.filter(key=v[0], file_name=Path(v[1]).name, file_type=v[2])
            self.assertTrue(sf.exists())
            expected_supporting_files.append({
                'filePath': v[1],
                'token': str(sf.first().token)
            }),

        expected = {
            'newBilbyJobFromIniString': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE=',
                    'supportingFiles': expected_supporting_files
                }
            }
        }

        response.data['newBilbyJobFromIniString']['result']['supportingFiles'].sort(key=lambda x: x['token'])
        expected['newBilbyJobFromIniString']['result']['supportingFiles'].sort(key=lambda x: x['token'])

        self.assertDictEqual(
            expected, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # And should create all k/v's with default values
        compare_ini_kvs(self, job, test_ini_string, config_names)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)

        # Job should not have been submitted as there is a supporting file
        self.assertIsNone(job.job_controller_id)

        # Now upload both files, checking that the job is only submitted once the last file upload has completed.
        def upload_supporting_file(token):
            content = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(128))

            f = SimpleUploadedFile(
                name='test.tar.gz',
                content=content.encode('utf-8')
            )

            file_input = {
                "input": {
                    "fileToken": token.token,
                    "supportingFile": f
                }
            }

            response = self.client.execute(
                self.supporting_file_mutation,
                file_input
            )

            self.assertTrue(response.data['uploadSupportingFile']['result']['result'])

        job.refresh_from_db()
        self.assertIsNone(job.job_controller_id)

        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(job.id)
        if job_dir.is_dir():
            shutil.rmtree(job_dir)

        for sf in supporting_files:
            job.refresh_from_db()
            self.assertIsNone(job.job_controller_id)

            upload_supporting_file(sf)
            self.assertTrue((Path(job_dir) / str(sf.id)).is_file())

        job.refresh_from_db()
        self.assertEqual(job.job_controller_id, 4321)

    def test_ini_job_submission_supporting_file_psd1(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'psd-dict': '{V1:./supporting_files/psd/V1-psd.dat}'
            },
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['V1', './supporting_files/psd/V1-psd.dat', SupportingFile.PSD]
            ],
            'psd_dict'
        )

    def test_ini_job_submission_supporting_file_psd2(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'psd-dict': '{L1:./supporting_files/psd/L1-psd.dat, V1:./supporting_files/psd/V1-psd.dat}'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['L1', './supporting_files/psd/L1-psd.dat', SupportingFile.PSD],
                ['V1', './supporting_files/psd/V1-psd.dat', SupportingFile.PSD]
            ],
            'psd_dict'
        )

    def test_ini_job_submission_supporting_file_psd3(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'psd-dict': '{L1:./supporting_files/psd/L1-psd.dat, V1:./supporting_files/psd/V1-psd.dat, '
                            'H1:./supporting_files/psd/H1-psd.dat}'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['L1', './supporting_files/psd/L1-psd.dat', SupportingFile.PSD],
                ['V1', './supporting_files/psd/V1-psd.dat', SupportingFile.PSD],
                ['H1', './supporting_files/psd/H1-psd.dat', SupportingFile.PSD]
            ],
            'psd_dict'
        )

    def test_ini_job_submission_supporting_file_calibration1(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'spline-calibration-envelope-dict': '{L1:./supporting_files/calib/L1-calib.dat}'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['L1', './supporting_files/calib/L1-calib.dat', SupportingFile.CALIBRATION]
            ],
            'spline_calibration_envelope_dict'
        )

    def test_ini_job_submission_supporting_file_calibration2(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'spline-calibration-envelope-dict': '{L1:./supporting_files/calib/L1-calib.dat, '
                                                    'V1:./supporting_files/calib/V1-calib.dat}'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['L1', './supporting_files/calib/L1-calib.dat', SupportingFile.CALIBRATION],
                ['V1', './supporting_files/calib/V1-calib.dat', SupportingFile.CALIBRATION]
            ],
            'spline_calibration_envelope_dict'
        )

    def test_ini_job_submission_supporting_file_calibration3(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'spline-calibration-envelope-dict': '{L1:./supporting_files/calib/L1-calib.dat, '
                                                    'V1:./supporting_files/calib/V1-calib.dat, '
                                                    'H1:./supporting_files/calib/H1-calib.dat}'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['L1', './supporting_files/calib/L1-calib.dat', SupportingFile.CALIBRATION],
                ['V1', './supporting_files/calib/V1-calib.dat', SupportingFile.CALIBRATION],
                ['H1', './supporting_files/calib/H1-calib.dat', SupportingFile.CALIBRATION]
            ],
            'spline_calibration_envelope_dict'
        )

    def test_ini_job_submission_supporting_file_prior(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'prior-file': './supporting_files/prior/myprior.prior'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                [None, './supporting_files/prior/myprior.prior', SupportingFile.PRIOR]
            ],
            'prior_file'
        )

    def test_ini_job_submission_supporting_file_gps(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'gps-file': './supporting_files/gps/gps.dat'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                [None, './supporting_files/gps/gps.dat', SupportingFile.GPS]
            ],
            'gps_file'
        )

    def test_ini_job_submission_supporting_file_timeslide(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'timeslide-file': './supporting_files/timeslide/timeslide.dat'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                [None, './supporting_files/timeslide/timeslide.dat', SupportingFile.TIME_SLIDE]
            ],
            'timeslide_file'
        )

    def test_ini_job_submission_supporting_file_injection(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'injection-file': './supporting_files/injection/injection.dat'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                [None, './supporting_files/injection/injection.dat', SupportingFile.INJECTION]
            ],
            'injection_file'
        )

    def test_ini_job_submission_supporting_file_numerical_relativity_file(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'numerical-relativity-file': './supporting_files/nrf/nrf.dat'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                [None, './supporting_files/nrf/nrf.dat', SupportingFile.NUMERICAL_RELATIVITY]
            ],
            'numerical_relativity_file'
        )

    def test_ini_job_submission_supporting_file_all(self):
        test_ini_string = create_test_ini_string(
            {
                'label': "Test Name",
                'detectors': "['H1']",
                'psd-dict': '{L1:./supporting_files/psd/L1-psd.dat, V1:./supporting_files/psd/V1-psd.dat, '
                            'H1:./supporting_files/psd/H1-psd.dat}',
                'spline-calibration-envelope-dict': '{L1:./supporting_files/calib/L1-calib.dat, '
                                                    'V1:./supporting_files/calib/V1-calib.dat, '
                                                    'H1:./supporting_files/calib/H1-calib.dat}',
                'prior-file': './supporting_files/prior/myprior.prior',
                'gps-file': './supporting_files/gps/gps.dat',
                'timeslide-file': './supporting_files/timeslide/timeslide.dat',
                'injection-file': './supporting_files/injection/injection.dat',
                'numerical-relativity-file': './supporting_files/nrf/nrf.dat'
            }
        )

        self.run_test_ini_job_submission_supporting_files(
            test_ini_string,
            [
                ['L1', './supporting_files/psd/L1-psd.dat', SupportingFile.PSD],
                ['V1', './supporting_files/psd/V1-psd.dat', SupportingFile.PSD],
                ['H1', './supporting_files/psd/H1-psd.dat', SupportingFile.PSD],

                ['L1', './supporting_files/calib/L1-calib.dat', SupportingFile.CALIBRATION],
                ['V1', './supporting_files/calib/V1-calib.dat', SupportingFile.CALIBRATION],
                ['H1', './supporting_files/calib/H1-calib.dat', SupportingFile.CALIBRATION],

                [None, './supporting_files/prior/myprior.prior', SupportingFile.PRIOR],

                [None, './supporting_files/gps/gps.dat', SupportingFile.GPS],

                [None, './supporting_files/timeslide/timeslide.dat', SupportingFile.TIME_SLIDE],

                [None, './supporting_files/injection/injection.dat', SupportingFile.INJECTION],

                [None, './supporting_files/nrf/nrf.dat', SupportingFile.NUMERICAL_RELATIVITY]
            ],
            [
                'psd_dict',
                'spline_calibration_envelope_dict',
                'prior_file',
                'gps_file',
                'timeslide_file',
                'injection_file',
                'numerical_relativity_file'
            ]
        )