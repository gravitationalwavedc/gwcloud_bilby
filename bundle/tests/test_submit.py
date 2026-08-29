import json
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import settings
from scheduler.scheduler import EScheduler
from testfixtures import Replacer, compare
from testfixtures.mock import call
from testfixtures.popen import MockPopen

from tests.utils import args_to_bilby_ini

update_job_result = None
get_unique_job_id_mock_return = None
working_directory_mock_return = None
submit_mock_return = None


def get_unique_job_id_mock_fn(*args, **kwargs):
    return get_unique_job_id_mock_return


def working_directory_mock_fn(*args, **kwargs):
    return working_directory_mock_return


def submit_mock_fn(*args, **kwargs):
    return submit_mock_return


def update_job_mock(job):
    """Mocked"""
    global update_job_result
    if not job["job_id"]:
        job["job_id"] = update_job_result

    update_job_result = job


class TestSubmit(TestCase):
    maxDiff = 0

    def setUp(self):
        self.popen = MockPopen()
        self.r = Replacer()
        self.r.replace("subprocess.Popen", self.popen)
        self.addCleanup(self.r.restore)

        # Wild hack to remove any trailing parameters which can influence bilby/condor job creation
        sys.argv = sys.argv[:1]

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.slurm.SlurmScheduler.submit", side_effect=submit_mock_fn)
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_submit_real_data_job_slurm(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini(
            {"label": "test-real", "detectors": ["H1"], "trigger-time": "12345678", "injection-numbers": []}
        ).decode("utf-8")

        details = {"job_id": 1}

        with TemporaryDirectory() as td:
            global working_directory_mock_return, submit_mock_return, update_job_result

            update_job_result = 4321

            working_directory_mock_return = td

            # Configure the popen data generation mock
            popen_command = f"/bin/bash {td}/submit/test-real_data0_12345678-0_generation.sh"
            self.popen.set_command(popen_command, stdout=b"stdout test", stderr=b"stderr test")

            # Local imports so that the mocks work as expected
            from core.submit import submit

            submit_mock_return = 1234

            params = {"name": "test-real", "description": "Some description", "ini_string": ini}

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, 4321)

            # Check that the internal job object was correctly created
            self.assertEqual(update_job_result["job_id"], 4321)
            self.assertEqual(update_job_result["submit_id"], submit_mock_return)
            self.assertEqual(update_job_result["working_directory"], td)
            self.assertEqual(update_job_result["submit_directory"], "./submit")

            # Check that the job script generation successfully called the the popen command
            process = call.Popen(popen_command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, cwd=td, shell=True)
            compare(self.popen.all_calls, expected=[process, process.communicate(), process.wait()])

            # Check the stdout and stderr logs for the data generation step are correctly written to their respective
            # log files
            with open(os.path.join(td, "log_data_generation", "test-real_data0_12345678-0_generation.out"), "rb") as f:
                self.assertEqual(f.read(), b"stdout test")

            with open(os.path.join(td, "log_data_generation", "test-real_data0_12345678-0_generation.err"), "rb") as f:
                self.assertEqual(f.read(), b"stderr test")

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, "submit", "slurm_test-real_master.sh")) as f:
                self.assertEqual(
                    f.read(),
                    """#!/bin/bash
#SBATCH --time=00:10:00
#SBATCH --output=./submit/test-real_master_slurm.out
#SBATCH --error=./submit/test-real_master_slurm.err

jid1=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=7-00:00:00 --job-name=test-real_data0_12345678-0_analysis_H1  --output=log_data_analysis/test-real_data0_12345678-0_analysis_H1.out --error=log_data_analysis/test-real_data0_12345678-0_analysis_H1.err ./submit/test-real_data0_12345678-0_analysis_H1.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids

jid2=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=4G --time=1:00:00 --job-name=test-real_data0_12345678-0_analysis_H1_final_result --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-real_data0_12345678-0_analysis_H1_final_result.out --error=log_data_analysis/test-real_data0_12345678-0_analysis_H1_final_result.err ./submit/test-real_data0_12345678-0_analysis_H1_final_result.sh))

echo "jid2 ${jid2[-1]}" >> ./submit/slurm_ids

jid3=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=32G --time=1:00:00 --job-name=test-real_data0_12345678-0_analysis_H1_plot --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-real_data0_12345678-0_analysis_H1_plot.out --error=log_data_analysis/test-real_data0_12345678-0_analysis_H1_plot.err ./submit/test-real_data0_12345678-0_analysis_H1_plot.sh))

echo "jid3 ${jid3[-1]}" >> ./submit/slurm_ids
""",
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, "test-real_config_complete.ini")) as f:
                    from core.submit import bilby_ini_to_args

                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, "test-real")
                self.assertEqual(args.detectors, ["'H1'"])
                self.assertEqual(args.trigger_time, "12345678")
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 2147483647)
                self.assertEqual(args.scheduler, settings.scheduler.value)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)
                self.assertEqual(args.transfer_files, False)

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.slurm.SlurmScheduler.submit", side_effect=submit_mock_fn)
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_submit_simulated_data_job_slurm(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini(
            {
                "label": "test-simulated",
                "detectors": ["H1", "V1"],
                "trigger-time": "87654321",
                "n-simulation": 1,
                "gaussian_noise": True,
                "injection-numbers": [],
            }
        ).decode("utf-8")

        details = {"job_id": 1}

        with TemporaryDirectory() as td:
            global working_directory_mock_return, submit_mock_return, update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Configure the popen data generation mock
            popen_command = f"/bin/bash {td}/submit/test-simulated_data0_12345678-0_generation.sh"
            self.popen.set_command(popen_command, stdout=b"stdout test", stderr=b"stderr test")

            # Local imports so that the mocks work as expected
            from core.submit import submit

            submit_mock_return = 12345

            params = {"name": "test-simulated", "description": "Some description", "ini_string": ini}

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, get_unique_job_id_mock_return)

            # Check that the internal job object was correctly created
            self.assertEqual(update_job_result["job_id"], get_unique_job_id_mock_return)
            self.assertEqual(update_job_result["submit_id"], submit_mock_return)
            self.assertEqual(update_job_result["working_directory"], td)
            self.assertEqual(update_job_result["submit_directory"], "./submit")

            # Check that the job script generation did not call the the popen command
            compare(self.popen.all_calls, expected=[])

            # Check the stdout and stderr logs for the data generation step do not exist
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, "log_data_generation", "test-simulated_data0_12345678-0_generation.out")
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, "log_data_generation", "test-simulated_data0_12345678-0_generation.err")
                )
            )

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, "submit", "slurm_test-simulated_master.sh")) as f:
                self.assertEqual(
                    f.read(),
                    """#!/bin/bash
#SBATCH --time=00:10:00
#SBATCH --output=./submit/test-simulated_master_slurm.out
#SBATCH --error=./submit/test-simulated_master_slurm.err

jid0=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=1:00:00 --job-name=test-simulated_data0_87654321-0_generation  --output=log_data_generation/test-simulated_data0_87654321-0_generation.out --error=log_data_generation/test-simulated_data0_87654321-0_generation.err ./submit/test-simulated_data0_87654321-0_generation.sh))

echo "jid0 ${jid0[-1]}" >> ./submit/slurm_ids

jid1=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=7-00:00:00 --job-name=test-simulated_data0_87654321-0_analysis_H1V1 --dependency=afterok:${jid0[-1]} --output=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1.out --error=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1.err ./submit/test-simulated_data0_87654321-0_analysis_H1V1.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids

jid2=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=4G --time=1:00:00 --job-name=test-simulated_data0_87654321-0_analysis_H1V1_final_result --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_final_result.out --error=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_final_result.err ./submit/test-simulated_data0_87654321-0_analysis_H1V1_final_result.sh))

echo "jid2 ${jid2[-1]}" >> ./submit/slurm_ids

jid3=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=32G --time=1:00:00 --job-name=test-simulated_data0_87654321-0_analysis_H1V1_plot --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_plot.out --error=log_data_analysis/test-simulated_data0_87654321-0_analysis_H1V1_plot.err ./submit/test-simulated_data0_87654321-0_analysis_H1V1_plot.sh))

echo "jid3 ${jid3[-1]}" >> ./submit/slurm_ids
""",
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, "test-simulated_config_complete.ini")) as f:
                    from core.submit import bilby_ini_to_args

                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, "test-simulated")
                self.assertEqual(args.detectors, ["'H1'", "'V1'"])
                self.assertEqual(args.trigger_time, "87654321")
                self.assertEqual(args.n_simulation, 1)
                self.assertEqual(args.gaussian_noise, True)
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 2147483647)
                self.assertEqual(args.scheduler, settings.scheduler.value)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)
                self.assertEqual(args.transfer_files, False)

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.slurm.SlurmScheduler.submit", side_effect=submit_mock_fn)
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_submit_simulated_data_job_submission_error_slurm(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini(
            {
                "label": "test-simulated-submission-failure",
                "detectors": ["V1", "L1"],
                "trigger-time": "11111111",
                "n-simulation": 1,
                "gaussian_noise": True,
                "injection-numbers": [],
            }
        ).decode("utf-8")

        details = {"job_id": 1}

        with TemporaryDirectory() as td:
            global working_directory_mock_return, submit_mock_return, update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Configure the popen data generation mock
            popen_command = f"/bin/bash {td}/submit/test-simulated_data0_12345678-0_generation.sh"
            self.popen.set_command(popen_command, stdout=b"stdout test", stderr=b"stderr test")

            # Local imports so that the mocks work as expected
            from core.submit import submit

            submit_mock_return = None

            params = {"name": "test-simulated-submission-failure", "description": "Some description", "ini_string": ini}

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
                    os.path.join(td, "log_data_generation", "test-simulated_data0_12345678-0_generation.out")
                )
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(td, "log_data_generation", "test-simulated_data0_12345678-0_generation.err")
                )
            )

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, "submit", "slurm_test-simulated-submission-failure_master.sh")) as f:
                self.assertEqual(
                    f.read(),
                    """#!/bin/bash
#SBATCH --time=00:10:00
#SBATCH --output=./submit/test-simulated-submission-failure_master_slurm.out
#SBATCH --error=./submit/test-simulated-submission-failure_master_slurm.err

jid0=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=1:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_generation  --output=log_data_generation/test-simulated-submission-failure_data0_11111111-0_generation.out --error=log_data_generation/test-simulated-submission-failure_data0_11111111-0_generation.err ./submit/test-simulated-submission-failure_data0_11111111-0_generation.sh))

echo "jid0 ${jid0[-1]}" >> ./submit/slurm_ids

jid1=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=8G --time=7-00:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_analysis_L1V1 --dependency=afterok:${jid0[-1]} --output=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1.out --error=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1.err ./submit/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids

jid2=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=4G --time=1:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_final_result --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_final_result.out --error=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_final_result.err ./submit/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_final_result.sh))

echo "jid2 ${jid2[-1]}" >> ./submit/slurm_ids

jid3=($(sbatch  --nodes=1 --ntasks-per-node=1 --mem=32G --time=1:00:00 --job-name=test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_plot --dependency=afterok:${jid1[-1]} --output=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_plot.out --error=log_data_analysis/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_plot.err ./submit/test-simulated-submission-failure_data0_11111111-0_analysis_L1V1_plot.sh))

echo "jid3 ${jid3[-1]}" >> ./submit/slurm_ids
""",
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, "test-simulated-submission-failure_config_complete.ini")) as f:
                    from core.submit import bilby_ini_to_args

                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, "test-simulated-submission-failure")
                self.assertEqual(args.detectors, ["'V1'", "'L1'"])
                self.assertEqual(args.trigger_time, "11111111")
                self.assertEqual(args.n_simulation, 1)
                self.assertEqual(args.gaussian_noise, True)
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 2147483647)
                self.assertEqual(args.scheduler, settings.scheduler.value)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)
                self.assertEqual(args.transfer_files, False)

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("core.submit.get_scheduler", return_value=None)
    @patch.object(settings, "scheduler", EScheduler.SLURM)
    def test_submit_unknown_scheduler_returns_none(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini(
            {
                "label": "test-unknown-scheduler",
                "detectors": ["H1"],
                "trigger-time": "12345678",
                "n-simulation": 1,
                "gaussian_noise": True,
                "injection-numbers": [],
            }
        ).decode("utf-8")

        details = {"job_id": 1}

        with TemporaryDirectory() as td:
            global working_directory_mock_return, update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Some bilby_pipe versions probe the CPU architecture via `uname -p` during dag generation
            self.popen.set_command("uname -p", stdout=b"x86_64")

            # Local imports so that the mocks work as expected
            from core.submit import submit

            params = {"name": "test-unknown-scheduler", "description": "Some description", "ini_string": ini}

            result = submit(details, json.dumps(params))

            # Check that the return value is None when the scheduler is unknown
            self.assertEqual(result, None)

            # Check that the internal job object was not created
            self.assertEqual(update_job_result, None)

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.condor.CondorScheduler.submit", side_effect=submit_mock_fn)
    @patch.object(settings, "scheduler", EScheduler.CONDOR)
    def test_submit_real_data_job_condor(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini(
            {"label": "test-real", "detectors": ["H1"], "trigger-time": "12345678", "injection-numbers": []}
        ).decode("utf-8")

        details = {"job_id": 1}

        with TemporaryDirectory() as td:
            global working_directory_mock_return, submit_mock_return, update_job_result

            working_directory_mock_return = td

            # Local imports so that the mocks work as expected
            from core.submit import submit

            submit_mock_return = 1234
            update_job_result = 4321

            params = {"name": "test-real", "description": "Some description", "ini_string": ini}

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, 4321)

            # Check that the internal job object was correctly created
            self.assertEqual(update_job_result["job_id"], 4321)
            self.assertEqual(update_job_result["submit_id"], submit_mock_return)
            self.assertEqual(update_job_result["working_directory"], td)
            self.assertEqual(update_job_result["submit_directory"], "./submit")

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, "submit", "dag_test-real.submit")) as f:
                self.assertEqual(
                    f.read(),
                    """JOB test-real_data0_12345678-0_generation_arg_0 ./submit/test-real_data0_12345678-0_generation.submit
VARS test-real_data0_12345678-0_generation_arg_0 ARGS="./test-real_config_complete.ini --label test-real_data0_12345678-0_generation --idx 0 --trigger-time 12345678.0"
JOB test-real_data0_12345678-0_analysis_H1_arg_0 ./submit/test-real_data0_12345678-0_analysis_H1.submit
VARS test-real_data0_12345678-0_analysis_H1_arg_0 ARGS="./test-real_config_complete.ini --detectors H1 --label test-real_data0_12345678-0_analysis_H1 --data-dump-file ./data/test-real_data0_12345678-0_generation_data_dump.pickle --sampler dynesty"
JOB test-real_data0_12345678-0_analysis_H1_final_result_arg_0 ./submit/test-real_data0_12345678-0_analysis_H1_final_result.submit
VARS test-real_data0_12345678-0_analysis_H1_final_result_arg_0 ARGS="--result ./result/test-real_data0_12345678-0_analysis_H1_result.hdf5 --outdir ./final_result --extension hdf5 --max-samples 20000 --lightweight --save"
JOB test-real_data0_12345678-0_analysis_H1_plot_arg_0 ./submit/test-real_data0_12345678-0_analysis_H1_plot.submit
VARS test-real_data0_12345678-0_analysis_H1_plot_arg_0 ARGS="--result ./result/test-real_data0_12345678-0_analysis_H1_result.hdf5 --outdir ./result --corner --marginal --skymap --waveform --format png"

#Inter-job dependencies
Parent test-real_data0_12345678-0_generation_arg_0 Child test-real_data0_12345678-0_analysis_H1_arg_0
Parent test-real_data0_12345678-0_analysis_H1_arg_0 Child test-real_data0_12345678-0_analysis_H1_final_result_arg_0
Parent test-real_data0_12345678-0_analysis_H1_arg_0 Child test-real_data0_12345678-0_analysis_H1_plot_arg_0""",
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, "test-real_config_complete.ini")) as f:
                    from core.submit import bilby_ini_to_args

                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, "test-real")
                self.assertEqual(args.detectors, ["'H1'"])
                self.assertEqual(args.trigger_time, "12345678")
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 28800)
                self.assertEqual(args.scheduler, settings.scheduler.value)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)
                self.assertEqual(args.accounting, "no.group")
                self.assertEqual(args.transfer_files, False)

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    def test_run_data_generation_without_output_flags(self, *args, **kwargs):
        # A data generation command without --output= or --error= flags should run the
        # generation script without attempting to write output/error files
        with TemporaryDirectory() as td:
            script = os.path.join(td, "data_gen.sh")
            with open(script, "w") as f:
                f.write("#!/bin/bash\necho test\n")

            popen_command = f"/bin/bash {script}"
            self.popen.set_command(popen_command, stdout=b"stdout test", stderr=b"stderr test")

            from core.submit import run_data_generation

            run_data_generation("sbatch ./data_gen.sh", td)

            # No output/error files should have been written
            self.assertFalse(os.path.exists(os.path.join(td, "data_gen.sh.out")))
            self.assertFalse(os.path.exists(os.path.join(td, "data_gen.sh.err")))

    def test_refactor_slurm_data_generation_step_no_data_generation(self):
        # A master script without a data generation step should be returned unchanged
        # and the function should return None
        original = """#!/bin/bash
#SBATCH --time=00:10:00

jid1=($(sbatch --nodes=1 --job-name=test_data0_analysis --output=log_data_analysis/test_data0_analysis.out --error=log_data_analysis/test_data0_analysis.err ./submit/test_data0_analysis.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids
"""
        with TemporaryDirectory() as td:
            script = os.path.join(td, "master.sh")
            with open(script, "w") as f:
                f.write(original)

            from core.submit import refactor_slurm_data_generation_step

            result = refactor_slurm_data_generation_step(script)

            self.assertIsNone(result)

            with open(script) as f:
                self.assertEqual(f.read(), original)

    def test_refactor_slurm_data_generation_step_removes_data_generation(self):
        # A master script with a data generation step should have the data generation
        # command returned, and the script rewritten without the data generation job,
        # its echo, and the dependency on it
        original = """#!/bin/bash
#SBATCH --time=00:10:00

jid0=($(sbatch --nodes=1 --job-name=test_data0_generation --output=log_data_generation/test_data0_generation.out --error=log_data_generation/test_data0_generation.err ./submit/test_data0_generation.sh))

echo "jid0 ${jid0[-1]}" >> ./submit/slurm_ids

jid1=($(sbatch --nodes=1 --job-name=test_data0_analysis --dependency=afterok:${jid0[-1]} --output=log_data_analysis/test_data0_analysis.out --error=log_data_analysis/test_data0_analysis.err ./submit/test_data0_analysis.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids
"""
        expected = """#!/bin/bash
#SBATCH --time=00:10:00

jid1=($(sbatch --nodes=1 --job-name=test_data0_analysis  --output=log_data_analysis/test_data0_analysis.out --error=log_data_analysis/test_data0_analysis.err ./submit/test_data0_analysis.sh))

echo "jid1 ${jid1[-1]}" >> ./submit/slurm_ids
"""
        with TemporaryDirectory() as td:
            script = os.path.join(td, "master.sh")
            with open(script, "w") as f:
                f.write(original)

            from core.submit import refactor_slurm_data_generation_step

            result = refactor_slurm_data_generation_step(script)

            self.assertEqual(
                result,
                "jid0=($(sbatch --nodes=1 --job-name=test_data0_generation --output=log_data_generation/test_data0_generation.out --error=log_data_generation/test_data0_generation.err ./submit/test_data0_generation.sh))\n",
            )

            with open(script) as f:
                self.assertEqual(f.read(), expected)

    @patch("_bundledb.create_or_update_job", side_effect=update_job_mock)
    @patch("core.misc.working_directory", side_effect=working_directory_mock_fn)
    @patch("scheduler.condor.CondorScheduler.submit", side_effect=submit_mock_fn)
    @patch.object(settings, "scheduler", EScheduler.CONDOR)
    def test_submit_simulated_data_job_condor(self, *args, **kwargs):
        # Generate a minimal ini file
        ini = args_to_bilby_ini(
            {
                "label": "test-simulated",
                "detectors": ["H1", "V1"],
                "trigger-time": "87654321",
                "n-simulation": 1,
                "gaussian_noise": True,
                "injection-numbers": [],
            }
        ).decode("utf-8")

        details = {"job_id": 1}

        with TemporaryDirectory() as td:
            global working_directory_mock_return, submit_mock_return, update_job_result

            update_job_result = None

            working_directory_mock_return = td

            # Local imports so that the mocks work as expected
            from core.submit import submit

            submit_mock_return = 1234

            params = {"name": "test-real", "description": "Some description", "ini_string": ini}

            result = submit(details, json.dumps(params))

            # Check that the return value (The internal bundle submission id) is correct
            self.assertEqual(result, get_unique_job_id_mock_return)

            # Check that the internal job object was correctly created
            self.assertEqual(update_job_result["job_id"], get_unique_job_id_mock_return)
            self.assertEqual(update_job_result["submit_id"], submit_mock_return)
            self.assertEqual(update_job_result["working_directory"], td)
            self.assertEqual(update_job_result["submit_directory"], "./submit")

            # Check that the master slurm script was correctly modified
            with open(os.path.join(td, "submit", "dag_test-simulated.submit")) as f:
                self.assertEqual(
                    f.read(),
                    """JOB test-simulated_data0_87654321-0_generation_arg_0 ./submit/test-simulated_data0_87654321-0_generation.submit
VARS test-simulated_data0_87654321-0_generation_arg_0 ARGS="./test-simulated_config_complete.ini --label test-simulated_data0_87654321-0_generation --idx 0 --trigger-time 87654321.0"
JOB test-simulated_data0_87654321-0_analysis_H1V1_arg_0 ./submit/test-simulated_data0_87654321-0_analysis_H1V1.submit
VARS test-simulated_data0_87654321-0_analysis_H1V1_arg_0 ARGS="./test-simulated_config_complete.ini --detectors H1 --detectors V1 --label test-simulated_data0_87654321-0_analysis_H1V1 --data-dump-file ./data/test-simulated_data0_87654321-0_generation_data_dump.pickle --sampler dynesty"
JOB test-simulated_data0_87654321-0_analysis_H1V1_final_result_arg_0 ./submit/test-simulated_data0_87654321-0_analysis_H1V1_final_result.submit
VARS test-simulated_data0_87654321-0_analysis_H1V1_final_result_arg_0 ARGS="--result ./result/test-simulated_data0_87654321-0_analysis_H1V1_result.hdf5 --outdir ./final_result --extension hdf5 --max-samples 20000 --lightweight --save"
JOB test-simulated_data0_87654321-0_analysis_H1V1_plot_arg_0 ./submit/test-simulated_data0_87654321-0_analysis_H1V1_plot.submit
VARS test-simulated_data0_87654321-0_analysis_H1V1_plot_arg_0 ARGS="--result ./result/test-simulated_data0_87654321-0_analysis_H1V1_result.hdf5 --outdir ./result --corner --marginal --skymap --waveform --format png"

#Inter-job dependencies
Parent test-simulated_data0_87654321-0_generation_arg_0 Child test-simulated_data0_87654321-0_analysis_H1V1_arg_0
Parent test-simulated_data0_87654321-0_analysis_H1V1_arg_0 Child test-simulated_data0_87654321-0_analysis_H1V1_final_result_arg_0
Parent test-simulated_data0_87654321-0_analysis_H1V1_arg_0 Child test-simulated_data0_87654321-0_analysis_H1V1_plot_arg_0""",
                )

                # Check that the ini file was correctly updated
                with open(os.path.join(td, "test-simulated_config_complete.ini")) as f:
                    from core.submit import bilby_ini_to_args

                    args = bilby_ini_to_args(f.read())

                self.assertEqual(args.label, "test-simulated")
                self.assertEqual(args.detectors, ["'H1'", "'V1'"])
                self.assertEqual(args.trigger_time, "87654321")
                self.assertEqual(args.n_simulation, 1)
                self.assertEqual(args.gaussian_noise, True)
                self.assertEqual(args.outdir, td)
                self.assertEqual(args.periodic_restart_time, 28800)
                self.assertEqual(args.scheduler, settings.scheduler.value)
                self.assertEqual(args.scheduler_env, settings.scheduler_env)
                self.assertEqual(args.accounting, "no.group")
                self.assertEqual(args.transfer_files, False)
