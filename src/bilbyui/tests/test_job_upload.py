import json
import os.path
import uuid
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from bilbyui.models import BilbyJob, IniKeyValue
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

    response = client.execute(
        generate_job_upload_token_mutation
    )

    return response


class TestJobUpload(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

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
        self.assertEqual(response.errors[0].message, 'You do not have permission to perform this action')

        self.client.authenticate(self.user, is_ligo=True)

        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id + 1]):
            response = get_upload_token(self.client)
            self.assertEqual(response.errors[0].message, 'User is not permitted to upload jobs')

        test_name = "Test Name"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                'label': test_name,
            }
        )

        test_file = SimpleUploadedFile(
            name='test.tar.gz',
            content=create_test_upload_data(test_ini_string, test_name),
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": uuid.uuid4(),
                "details": {
                    "name": test_name,
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        self.assertEqual(response.errors[0].message, 'Job upload token is invalid or expired.')

        self.assertDictEqual(
            {'uploadBilbyJob': None},
            response.data
        )

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_success(self):
        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

        test_name = "myjob"
        test_description = "Test Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                'label': test_name,
                'outdir': './'
            },
            True
        )

        test_file = SimpleUploadedFile(
            name='test.tar.gz',
            content=create_test_upload_data(test_ini_string, test_name),
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        expected = {
            'uploadBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.assertDictEqual(
            expected,
            response.data
        )

        # And should create all k/v's with default values
        job = BilbyJob.objects.all().last()
        compare_ini_kvs(self, job, test_ini_string)

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)

        # Check that the output directories and ini file were correctly created
        job_dir = job.get_upload_directory()
        self.assertTrue(os.path.isdir(job_dir))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, 'data')))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, 'result')))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, 'results_page')))
        self.assertTrue(os.path.isfile(os.path.join(job_dir, 'myjob_config_complete.ini')))

        self.assertTrue(os.path.isfile(os.path.join(job_dir, 'archive.tar.gz')))

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    def test_job_upload_success_outdir_replace(self):
        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

        test_name = "another_job"
        test_description = "Another Description"
        test_private = True

        test_ini_string = create_test_ini_string(
            {
                'label': test_name,
                'outdir': '/some/path/not/good/'
            },
            True
        )

        test_file = SimpleUploadedFile(
            name='anothertest.tar.gz',
            content=create_test_upload_data(test_ini_string, test_name),
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        expected = {
            'uploadBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.assertDictEqual(
            expected,
            response.data
        )

        job = BilbyJob.objects.all().last()
        self.assertTrue(
            IniKeyValue.objects.filter(
                job=job,
                key='outdir',
                value=json.dumps('./')
            ).exists()
        )

        self.assertEqual(job.name, test_name)
        self.assertEqual(job.description, test_description)
        self.assertEqual(job.private, test_private)

        # Check that the output directories and ini file were correctly created
        job_dir = job.get_upload_directory()
        self.assertTrue(os.path.isdir(job_dir))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, 'data')))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, 'result')))
        self.assertTrue(os.path.isdir(os.path.join(job_dir, 'results_page')))
        self.assertTrue(os.path.isfile(os.path.join(job_dir, 'another_job_config_complete.ini')))

        self.assertTrue(os.path.isfile(os.path.join(job_dir, 'archive.tar.gz')))

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_missing_data(self):
        for missing_dir in ['data', 'result', 'results_page']:
            with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
                token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

            test_name = missing_dir
            test_description = f"{missing_dir} Description"
            test_private = False

            test_ini_string = create_test_ini_string(
                {
                    'label': test_name,
                },
                True
            )

            test_file = SimpleUploadedFile(
                name='test.tar.gz',
                content=create_test_upload_data(test_ini_string, test_name, **{f'include_{missing_dir}': False}),
                content_type='application/gzip'
            )

            test_input = {
                "input": {
                    "uploadToken": token,
                    "details": {
                        "description": test_description,
                        "private": test_private
                    },
                    "jobFile": test_file
                }
            }

            response = self.client.execute(
                self.mutation,
                test_input
            )

            self.assertEqual(
                f"Invalid directory structure, expected directory ./{missing_dir} to exist.",
                response.errors[0].message
            )

            self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_missing_ini(self):
        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

        test_name = "missing_ini"
        test_description = "Missing Ini Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                'label': test_name,
            },
            True
        )

        test_file = SimpleUploadedFile(
            name='test.tar.gz',
            content=create_test_upload_data(test_ini_string, test_name, no_ini_file=True),
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        self.assertEqual(
            "Invalid number of ini files ending in `_config_complete.ini`. There should be exactly one.",
            response.errors[0].message
        )

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_upload_many_ini(self):
        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

        test_name = "missing_ini"
        test_description = "Missing Ini Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                'label': test_name,
            },
            True
        )

        test_file = SimpleUploadedFile(
            name='test.tar.gz',
            content=create_test_upload_data(test_ini_string, test_name, multiple_ini_files=True),
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        self.assertEqual(
            "Invalid number of ini files ending in `_config_complete.ini`. There should be exactly one.",
            response.errors[0].message
        )

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_invalid_tar_gz_name(self):
        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

        test_name = "invalid_tar_gz_name"
        test_description = "Invalid .tar.gz Name Description"
        test_private = False

        test_ini_string = create_test_ini_string(
            {
                'label': test_name,
            },
            True
        )

        test_file = SimpleUploadedFile(
            name='test.tar.g',
            content=create_test_upload_data(test_ini_string, test_name, no_ini_file=True),
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        self.assertEqual(
            "Job upload should be a tar.gz file",
            response.errors[0].message
        )

        self.assertFalse(BilbyJob.objects.all().exists())

    @override_settings(JOB_UPLOAD_DIR=TemporaryDirectory().name)
    @silence_errors
    def test_job_corrupt_tar_gz(self):
        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']

        test_description = "Corrupt .tar.gz Description"
        test_private = False

        test_file = SimpleUploadedFile(
            name='test.tar.gz',
            content=b'1234567abcdefg',
            content_type='application/gzip'
        )

        test_input = {
            "input": {
                "uploadToken": token,
                "details": {
                    "description": test_description,
                    "private": test_private
                },
                "jobFile": test_file
            }
        }

        response = self.client.execute(
            self.mutation,
            test_input
        )

        self.assertEqual(
            "Invalid or corrupt tar.gz file",
            response.errors[0].message
        )

        self.assertFalse(BilbyJob.objects.all().exists())


class TestJobUploadLigoPermissions(BilbyTestCase):
    def setUp(self):
        self.maxDiff = 9999

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

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
            "input": {
                "details": {
                    "description": 'test_description',
                    "private": 'test_private'
                },
                "jobFile": None
            }
        }

        self.expected_one = {
            'uploadBilbyJob': {
                'result': {
                    'jobId': 'QmlsYnlKb2JOb2RlOjE='
                }
            }
        }

        self.expected_none = {
            'uploadBilbyJob': None
        }

    @silence_errors
    def test_non_ligo_user_with_gwosc(self):
        # Test checks that a LIGO user does not create a LIGO job if the data is real and channels are GWOSC
        self.client.authenticate(self.user, is_ligo=False)

        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']
            self.params['input']['uploadToken'] = token

        ini_string = create_test_ini_string(config_dict={
            'label': 'testjob',
            "n-simulation": 0,
            "channel-dict": {'H1': 'GWOSC', 'L1': 'GWOSC'}
        }, complete=True)

        self.params['input']['jobFile'] = SimpleUploadedFile(
            name='test.tar.gz',
            content=create_test_upload_data(ini_string, 'testjob'),
            content_type='application/gzip'
        )

        response = self.client.execute(self.mutation, self.params)

        self.assertDictEqual(
            self.expected_one, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_ligo_user_with_gwosc(self):
        # This test checks that a non LIGO user can still create non LIGO jobs
        self.client.authenticate(self.user, is_ligo=True)

        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']
            self.params['input']['uploadToken'] = token

        ini_string = create_test_ini_string(config_dict={
            'label': 'testjob',
            "n-simulation": 0,
            "channel-dict": {'H1': 'GWOSC', 'L1': 'GWOSC'}
        }, complete=True)

        self.params['input']['jobFile'] = SimpleUploadedFile(
            name='test.tar.gz',
            content=create_test_upload_data(ini_string, 'testjob'),
            content_type='application/gzip'
        )

        response = self.client.execute(self.mutation, self.params)

        self.assertDictEqual(
            self.expected_one, response.data, "create bilbyJob mutation returned unexpected data."
        )

        # Check that the job is marked as not proprietary
        self.assertFalse(BilbyJob.objects.all().last().is_ligo_job)

    @silence_errors
    def test_non_ligo_user_with_non_gwosc(self):
        # Test checks that non-LIGO user cannot create real jobs with non-GWOSC channels, nor with invalid channels
        # Now if the channels are proprietary, the non-ligo user should not be able to create jobs
        self.client.authenticate(self.user, is_ligo=False)

        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']
            self.params['input']['uploadToken'] = token

        for channel_dict in [
            {'H1': 'GDS-CALIB_STRAIN', 'L1': 'GWOSC', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GDS-CALIB_STRAIN', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GWOSC', 'V1': 'Hrec_hoft_16384Hz'},
            # Also check invalid channels
            {'H1': 'testchannel1', 'L1': 'GWOSC', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'imnotarealchannel', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GWOSC', 'V1': 'GWOSc'},
        ]:
            ini_string = create_test_ini_string({
                'label': 'testjob',
                'n-simulation': 0,
                'channel-dict': channel_dict
            }, complete=True)

            self.params['input']['jobFile'] = SimpleUploadedFile(
                name='test.tar.gz',
                content=create_test_upload_data(ini_string, 'testjob'),
                content_type='application/gzip'
            )

            response = self.client.execute(self.mutation, self.params)

            self.assertDictEqual(
                self.expected_none, response.data, "create bilbyJob mutation returned unexpected data."
            )

            self.assertEqual(
                response.errors[0].message,
                'Non-LIGO members may only upload real jobs on GWOSC channels'
            )

            self.assertFalse(BilbyJob.objects.all().exists())

    @silence_errors
    def test_ligo_user_with_non_gwosc(self):
        # Test that LIGO users can make jobs with proprietary channels
        # Now if the channels are proprietary, the ligo user should be able to create jobs
        self.client.authenticate(self.user, is_ligo=True)

        with override_settings(PERMITTED_UPLOAD_USER_IDS=[self.user.id]):
            token = get_upload_token(self.client).data['generateBilbyJobUploadToken']['token']
            self.params['input']['uploadToken'] = token

        for channel_dict in [
            {'H1': 'GDS-CALIB_STRAIN', 'L1': 'GWOSC', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GDS-CALIB_STRAIN', 'V1': 'GWOSC'},
            {'H1': 'GWOSC', 'L1': 'GWOSC', 'V1': 'Hrec_hoft_16384Hz'},
        ]:
            ini_string = create_test_ini_string({
                'label': 'testjob',
                'n-simulation': 0,
                'channel-dict': channel_dict
            }, complete=True)

            self.params['input']['jobFile'] = SimpleUploadedFile(
                name='test.tar.gz',
                content=create_test_upload_data(ini_string, 'testjob'),
                content_type='application/gzip'
            )

            response = self.client.execute(self.mutation, self.params)

            self.assertTrue('jobId' in response.data['uploadBilbyJob']['result'])

            # Check that the job is marked as proprietary
            job = BilbyJob.objects.all().last()
            self.assertTrue(job.is_ligo_job)
            job.delete()
