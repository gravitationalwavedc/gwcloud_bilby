import json
import os
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from testfixtures import compare, Replacer
from testfixtures.mock import call
from testfixtures.popen import MockPopen

import settings
from tests.utils import args_to_bilby_ini

update_job_result = None
get_unique_job_id_mock_return = None
working_directory_mock_return = None
slurm_submit_mock_return = None


def get_unique_job_id_mock_fn(*args, **kwargs):
    return get_unique_job_id_mock_return


def working_directory_mock_fn(*args, **kwargs):
    return working_directory_mock_return


def slurm_submit_mock_fn(*args, **kwargs):
    return slurm_submit_mock_return


def update_job_mock(job):
    """Mocked"""
    global update_job_result
    update_job_result = job


class TestSubmit(TestCase):
    def setUp(self):
        self.popen = MockPopen()
        self.r = Replacer()
        self.r.replace('subprocess.Popen', self.popen)
        self.addCleanup(self.r.restore)

    @patch('db.update_job', side_effect=update_job_mock)
    @patch("db.get_unique_job_id", side_effect=get_unique_job_id_mock_fn)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.slurm.SlurmScheduler.submit", side_effect=slurm_submit_mock_fn)
    def test_submit_real_data_job(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini({
            'label': 'test-real',
            'detectors': ['H1'],
            'trigger-time': '12345678',
            'injection-numbers': []
        }).decode('utf-8')

        details = {
            'job_id': 1
        }

        with TemporaryDirectory() as td:
            global working_directory_mock_return, get_unique_job_id_mock_return, slurm_submit_mock_return, \
                update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Configure the popen data generation mock
            popen_command = f'/bin/bash {td}/submit/test-real_data0_12345678-0_generation.sh'
            self.popen.set_command(
                popen_command,
                stdout=b'stdout test',
                stderr=b'stderr test'
            )

            # Local imports so that the mocks work as expected
            from core.submit import submit

            slurm_submit_mock_return = 1234
            get_unique_job_id_mock_return = 4321

            params = dict(
                name='test-real',
                description='Some description',
                ini_string=ini
            )

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, get_unique_job_id_mock_return)

            # Check that the internal job object was correctly created
            self.assertEqual(update_job_result['job_id'], get_unique_job_id_mock_return)
            self.assertEqual(update_job_result['submit_id'], slurm_submit_mock_return)
            self.assertEqual(update_job_result['working_directory'], td)
            self.assertEqual(update_job_result['submit_directory'], './submit')

            # Check that the job script generation successfully called the the popen command
            process = call.Popen(popen_command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, cwd=td, shell=True)
            compare(self.popen.all_calls, expected=[
                process,
                process.wait(),
                process.communicate(),
                process.wait()
            ])

            # Check the stdout and stderr logs for the data generation step are correctly written to their respective
            # log files
            with open(os.path.join(td, 'log_data_generation', 'test-real_data0_12345678-0_generation.out'), 'rb') as f:
                self.assertEqual(f.read(), b'stdout test')

            with open(os.path.join(td, 'log_data_generation', 'test-real_data0_12345678-0_generation.err'), 'rb') as f:
                self.assertEqual(f.read(), b'stderr test')

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, 'submit', 'slurm_test-real_master.sh'), 'r') as f:
                self.assertEqual(
                    f.read(),
                    """#!/bin/bash
#SBATCH --time=00:10:00
#SBATCH --output=./submit/test-real_master_slurm.out
#SBATCH --error=./submit/test-real_master_slurm.err

jid1=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=4G --time=7-00:00:00 --job-name=test-real_data0_12345678-0_analysis_H1_dynesty  --output=log_data_analysis/test-real_data0_12345678-0_analysis_H1_dynesty.out --error=log_data_analysis/test-real_data0_12345678-0_analysis_H1_dynesty.err ./submit/test-real_data0_12345678-0_analysis_H1_dynesty.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids

jid2=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=32G --time=1:00:00 --job-name=test-real_data0_12345678-0_analysis_H1_dynesty_plot --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-real_data0_12345678-0_analysis_H1_dynesty_plot.out --error=log_data_analysis/test-real_data0_12345678-0_analysis_H1_dynesty_plot.err ./submit/test-real_data0_12345678-0_analysis_H1_dynesty_plot.sh))

echo "jid2 ${jid2[-1]}" >> ./submit/slurm_ids
""" # noqa
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, 'test-real_config_complete.ini'), 'r') as f:
                    from core.submit import bilby_ini_to_args
                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, 'test-real')
                self.assertEqual(args.detectors, ["'H1'"])
                self.assertEqual(args.trigger_time, '12345678')
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 2147483647)
                self.assertEqual(args.scheduler, settings.scheduler)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)

    @patch('db.update_job', side_effect=update_job_mock)
    @patch("db.get_unique_job_id", side_effect=get_unique_job_id_mock_fn)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.slurm.SlurmScheduler.submit", side_effect=slurm_submit_mock_fn)
    def test_submit_simulated_data_job(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini({
            'label': 'test-simulated',
            'detectors': ['H1', 'V1'],
            'trigger-time': '87654321',
            'n-simulation': 1,
            'gaussian_noise': True,
            'injection-numbers': []
        }).decode('utf-8')

        details = {
            'job_id': 1
        }

        with TemporaryDirectory() as td:
            global working_directory_mock_return, get_unique_job_id_mock_return, slurm_submit_mock_return, \
                update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Configure the popen data generation mock
            popen_command = f'/bin/bash {td}/submit/test-simulated_data0_12345678-0_generation.sh'
            self.popen.set_command(
                popen_command,
                stdout=b'stdout test',
                stderr=b'stderr test'
            )

            # Local imports so that the mocks work as expected
            from core.submit import submit

            slurm_submit_mock_return = 12345
            get_unique_job_id_mock_return = 54321

            params = dict(
                name='test-simulated',
                description='Some description',
                ini_string=ini
            )

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, get_unique_job_id_mock_return)

            # Check that the internal job object was correctly created
            self.assertEqual(update_job_result['job_id'], get_unique_job_id_mock_return)
            self.assertEqual(update_job_result['submit_id'], slurm_submit_mock_return)
            self.assertEqual(update_job_result['working_directory'], td)
            self.assertEqual(update_job_result['submit_directory'], './submit')

            # Check that the job script generation did not call the the popen command
            compare(self.popen.all_calls, expected=[])

            # Check the stdout and stderr logs for the data generation step do not exist
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, 'log_data_generation', 'test-simulated_data0_12345678-0_generation.out')
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, 'log_data_generation', 'test-simulated_data0_12345678-0_generation.err')
                )
            )

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, 'submit', 'slurm_test-simulated_master.sh'), 'r') as f:
                self.assertEqual(
                    f.read(),
                    """#!/bin/bash
#SBATCH --time=00:10:00
#SBATCH --output=./submit/test-simulated_master_slurm.out
#SBATCH --error=./submit/test-simulated_master_slurm.err

jid0=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=1:00:00 --job-name=test-simulated_data0_87654321-0_generation  --output=log_data_generation/test-simulated_data0_87654321-0_generation.out --error=log_data_generation/test-simulated_data0_87654321-0_generation.err ./submit/test-simulated_data0_87654321-0_generation.sh))

echo "jid0 ${jid0[-1]}" >> ./submit/slurm_ids

jid1=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=4G --time=7-00:00:00 --job-name=test-simulated_data0_87654321-0_analysis_H1V1_dynesty --dependency=afterok:${jid0[-1]} --output=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_dynesty.out --error=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_dynesty.err ./submit/test-simulated_data0_87654321-0_analysis_H1V1_dynesty.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids

jid2=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=32G --time=1:00:00 --job-name=test-simulated_data0_87654321-0_analysis_H1V1_dynesty_plot --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_dynesty_plot.out --error=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_dynesty_plot.err ./submit/test-simulated_data0_87654321-0_analysis_H1V1_dynesty_plot.sh))

echo "jid2 ${jid2[-1]}" >> ./submit/slurm_ids
""" # noqa
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, 'test-simulated_config_complete.ini'), 'r') as f:
                    from core.submit import bilby_ini_to_args
                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, 'test-simulated')
                self.assertEqual(args.detectors, ["'H1'", "'V1'"])
                self.assertEqual(args.trigger_time, '87654321')
                self.assertEqual(args.n_simulation, 1)
                self.assertEqual(args.gaussian_noise, True)
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 2147483647)
                self.assertEqual(args.scheduler, settings.scheduler)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)

    @patch('db.update_job', side_effect=update_job_mock)
    @patch("db.get_unique_job_id", side_effect=get_unique_job_id_mock_fn)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.slurm.SlurmScheduler.submit", side_effect=slurm_submit_mock_fn)
    def test_submit_simulated_data_job_submission_error(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini({
            'label': 'test-simulated-submission-failure',
            'detectors': ['V1', 'L1'],
            'trigger-time': '11111111',
            'n-simulation': 1,
            'gaussian_noise': True,
            'injection-numbers': []
        }).decode('utf-8')

        details = {
            'job_id': 1
        }

        with TemporaryDirectory() as td:
            global working_directory_mock_return, slurm_submit_mock_return, \
                update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Configure the popen data generation mock
            popen_command = f'/bin/bash {td}/submit/test-simulated_data0_12345678-0_generation.sh'
            self.popen.set_command(
                popen_command,
                stdout=b'stdout test',
                stderr=b'stderr test'
            )

            # Local imports so that the mocks work as expected
            from core.submit import submit

            slurm_submit_mock_return = None

            params = dict(
                name='test-simulated-submission-failure',
                description='Some description',
                ini_string=ini
            )

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, None)

            # Check that the internal job object not created
            self.assertEqual(update_job_result, None)

            # Check that the job script generation did not call the the popen command
            compare(self.popen.all_calls, expected=[])

            # Check the stdout and stderr logs for the data generation step do not exist
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, 'log_data_generation', 'test-simulated_data0_12345678-0_generation.out')
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, 'log_data_generation', 'test-simulated_data0_12345678-0_generation.err')
                )
            )

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, 'submit', 'slurm_test-simulated-submission-failure_master.sh'), 'r') as f:
                self.assertEqual(
                    f.read(),
                    """#!/bin/bash
#SBATCH --time=00:10:00
#SBATCH --output=./submit/test-simulated-submission-failure_master_slurm.out
#SBATCH --error=./submit/test-simulated-submission-failure_master_slurm.err

jid0=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=1:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_generation  --output=log_data_generation/test-simulated-submission-failure_data0_11111111-0_generation.out --error=log_data_generation/test-simulated-submission-failure_data0_11111111-0_generation.err ./submit/test-simulated-submission-failure_data0_11111111-0_generation.sh))

echo "jid0 ${jid0[-1]}" >> ./submit/slurm_ids

jid1=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=4G --time=7-00:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty --dependency=afterok:${jid0[-1]} --output=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty.out --error=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty.err ./submit/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids

jid2=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=32G --time=1:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty_plot --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty_plot.out --error=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty_plot.err ./submit/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_dynesty_plot.sh))

echo "jid2 ${jid2[-1]}" >> ./submit/slurm_ids
""" # noqa
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, 'test-simulated-submission-failure_config_complete.ini'), 'r') as f:
                    from core.submit import bilby_ini_to_args
                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, 'test-simulated-submission-failure')
                self.assertEqual(args.detectors, ["'V1'", "'L1'"])
                self.assertEqual(args.trigger_time, '11111111')
                self.assertEqual(args.n_simulation, 1)
                self.assertEqual(args.gaussian_noise, True)
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 2147483647)
                self.assertEqual(args.scheduler, settings.scheduler)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)
