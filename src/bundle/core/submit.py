import json
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests
from bilby_pipe.job_creation.dag import Dag
from bilby_pipe.job_creation.slurm import SubmitSLURM
from bilby_pipe.main import MainInput, generate_dag
from bilby_pipe.parser import create_parser
from bilby_pipe.utils import parse_args

import settings
from core.misc import get_scheduler, working_directory
from db import get_next_unique_job_id, create_or_update_job
from scheduler.scheduler import EScheduler

chdir_lock = threading.Lock()


@contextmanager
def set_directory(path: Path):
    """Sets the cwd within the context

    Args:
        path (Path): The path to the cwd

    Yields:
        None
    """

    origin = Path().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


def bilby_ini_to_args(ini):
    """
    Parses an ini string in to an argument Namespace

    :params ini: The ini string to parse
    :return: An ArgParser Namespace of the parsed arguments from the ini
    """

    # Create a bilby argument parser
    parser = create_parser()

    # Bilby pipe requires a real file in order to parse the ini file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        f.write(ini.encode('utf-8'))

        # Make sure the data is written to the temporary file
        f.flush()

        # Read the data from the ini file
        args, unknown_args = parse_args([f.name], parser)

    return args


def prepare_supporting_files(bilby_args, supporting_files, working_directory):
    """
    Fetches any supporting files from GWCloud and writes them to disk, then configures the bilby_args object to
    point at the saved supporting files

    param: bilby_args: The bilby args object
    param: supporting_files: The supporting files for the job
    param: working_directory: The working directory for the job
    """
    for supporting_file in supporting_files:
        # Make sure that the output directory exists for the supporting file type
        supporting_file_dir = Path(working_directory) / 'supporting_files' / supporting_file['type']
        supporting_file_dir.mkdir(exist_ok=True, parents=True)

        # Request the file from the GWCloud and write it to disk
        file_download_url = f"https://gwcloud.org.au/bilby/file_download/?fileId={supporting_file['token']}"
        response = requests.get(file_download_url, allow_redirects=True)
        supporting_file_path = supporting_file_dir / supporting_file['file_name']
        supporting_file_path.write_bytes(response.content)

        # Finally prepare the bilby args
        file_type_map = {
            "psd": "psd_dict",
            "cal": "spline_calibration_envelope_dict",
            "pri": "prior_file",
            "gps": "gps_file",
            "tsl": "timeslide_file",
            "inj": "injection_file",
            "nmr": "numerical_relativity_file",
            "dml": "distance_marginalization_lookup_table"
        }

        # Need the path to the supporting file relative to the working directory
        relative_supporting_file_path = f'./{Path(supporting_file_path).relative_to(os.getcwd())}'

        # If this supporting file has a key, then the file is part of a dictionary, otherwise it's a single file
        if supporting_file['key']:
            # Pseudocode
            # if not bilby_args.psd_dict:
            #     bilby_args.psd_dict = {}
            # bilby_args.psd_dict[key] = relative_path_to_psd_file

            if not getattr(bilby_args, file_type_map[supporting_file['type']]):
                setattr(bilby_args, file_type_map[supporting_file['type']], {})

            getattr(
                bilby_args,
                file_type_map[supporting_file['type']]
            )[supporting_file['key']] = relative_supporting_file_path
        else:
            # Pseudocode
            # bilby_args.psd_dict = relative_path_to_psd_file

            setattr(bilby_args, file_type_map[supporting_file['type']], relative_supporting_file_path)


def prepare_ini_data(job_parameters, working_directory):
    """
    Takes the ini content generated by the UI and sanitizes and updates the ini file for execution as a job

    :param job_parameters: The original json object string sent from the UI
    :param working_directory: The working directory of the job
    :return: The updated args ready to be executed as a job
    """

    # Parse the json object from the ui
    job_parameters = json.loads(job_parameters)

    # Get the ini content
    ini = job_parameters['ini_string']

    # First parse the ini file to args
    args = bilby_ini_to_args(ini)

    # Next, override required arguments

    ################################################################################
    # Job submission arguments
    # How the jobs should be formatted, e.g., which job scheduler to use.
    ################################################################################

    if settings.scheduler == EScheduler.CONDOR:
        # Accounting group to use (see, https://accounting.ligo.org/user)
        args.accounting = settings.condor_accounting_group

        # Accounting group user to use (see, https://accounting.ligo.org/user)
        args.accounting_user = settings.condor_accounting_user

    # Output directory
    args.outdir = working_directory

    # Ignore transfer files because we're not using condor. This resolves the problem with relpath of the CWD path
    # being ".", which bilby_pipe refuses to use as a valid output directory
    args.transfer_files = False

    # Time after which the job will be self-evicted. After this, condor will restart the job. Default is 28800.
    # This is used to decrease the chance of HTCondor hard evictions
    if settings.scheduler == EScheduler.SLURM:
        args.periodic_restart_time = 2147483647
    else:
        args.periodic_restart_time = 28800

    # Format submission script for specified scheduler. Currently implemented: SLURM, CONDOR
    args.scheduler = settings.scheduler.value

    # Environment scheduler sources during runtime
    args.scheduler_env = settings.scheduler_env

    # Attempt to submit the job after the build - we submit the job as part of the scheduler functionality
    args.submit = False

    ################################################################################
    # Output arguments
    # What kind of output/summary to generate.
    ################################################################################

    # Create diagnostic and posterior plots
    args.create_plots = True

    # Create calibration posterior plot
    args.plot_calibration = False

    # Create intrinsic and extrinsic posterior corner plots
    args.plot_corner = True

    # Create 1-d marginal posterior plots
    args.plot_marginal = True

    # Create posterior skymap
    args.plot_skymap = True

    # Create waveform posterior plot
    args.plot_waveform = True

    # Format for making bilby_pipe plots, can be [png, pdf, html]. If specified format is not supported, will
    # default to png.
    args.plot_format = "png"

    # Create a PESummary page
    args.create_summary = False

    ################################################################################
    # Waveform arguments
    # Setting for the waveform generator
    ################################################################################

    # Turns on waveform error catching
    args.catch_waveform_errors = True

    # Configure supporting files
    if 'supporting_files' in job_parameters and job_parameters['supporting_files']:
        prepare_supporting_files(args, job_parameters['supporting_files'], working_directory)

    return args


def run_data_generation(data_gen_command, wk_dir):
    """
    Uses the original data generation step command to run the data generation step locally. This is done for jobs which
    require GWOSC or real data, since the data generation step can not be executed on a compute node.

    :param data_gen_command: The original data generation command
    :param wk_dir: The working directory of the job
    :return: Nothing
    """
    # Get the error and output log paths
    error_file = None
    output_file = None
    for bit in data_gen_command.split(' '):
        if '--error=' in bit:
            error_file = bit.split('--error=')[-1]

        if '--output' in bit:
            output_file = bit.split('--output=')[-1]

    # Get the last parameter to sbatch, which is the script to run to generate the data
    data_gen_command = data_gen_command.split(' ')[-1]

    # Remove the closing brackets
    data_gen_command = data_gen_command.replace(')', '')

    # Strip any newlines or whitespace
    data_gen_command = data_gen_command.strip()

    # Run the data generation
    os.sync()
    with subprocess.Popen(
            f"/bin/bash {os.path.abspath(os.path.join(wk_dir, data_gen_command))}",
            cwd=wk_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
    ) as p:
        p.wait()

        # Get the output from the data generation command
        stdout, stderr = p.communicate()

        # Write the data generation output to output files
        with open(Path(wk_dir) / output_file, "w") as f:
            f.write(stdout.decode())
        with open(Path(wk_dir) / error_file, "w") as f:
            f.write(stderr.decode())


def refactor_slurm_data_generation_step(slurm_script):
    """
    When using real or GWOSC data, the data generation step needs to be removed from the slurm jobs and executed
    locally. This function refactors the slurm master submission script to remove the data generation job step, and
    returns that command so it can be executed by this script.

    :param slurm_script: The path to the master slurm job submission script
    :return: The data generation command
    """
    # Read the lines from the submit script
    with open(slurm_script, 'r') as f:
        slines = f.readlines()

    # Find the line for data generation and the first echo after that, then remove the dependency from the following
    # sbatch command
    data_gen_idx = None
    data_gen_command = None
    new_lines = []
    generation_jid = None
    echo_found = False
    for line in slines:
        # Check for the sbatch command to generate the data
        if 'log_data_generation' in line:
            data_gen_idx = line
            data_gen_command = line
            generation_jid = data_gen_command.split('=')[0]

            # Nothing more to do, exclude this line from the new sbatch script
            continue

        # Check for the first echo command after the sbatch command
        if data_gen_idx and 'echo' in line and not echo_found:
            echo_found = True
            # Nothing more to do, exclude this line from the new sbatch script
            continue

        # Check if this line is the next sbatch command using jid0 as a
        if data_gen_idx and '--dependency=afterok:${' + generation_jid + '[-1]}' in line:
            # Remove the dependenc
            line = line.replace('--dependency=afterok:${' + generation_jid + '[-1]}', '')

        new_lines.append(line)

    # Replace any triple newlines with double newlines
    script_content = re.sub('\n\n+', '\n\n', ''.join(new_lines))

    # Write the updated lines to the job submission script
    with open(slurm_script, 'w') as f:
        f.write(script_content)

    return data_gen_command


def write_submission_scripts(inputs, wk_dir):
    """
    Writes the submission scripts using the MainInput inputs, and returns the slurm master script path

    :param inputs: The MainInput object with the complete input information for the job
    :return: The path to the master submit script
    """
    # Generate the submission scripts
    # Working directory changes need to be synchronous
    with chdir_lock, set_directory(wk_dir):
        generate_dag(inputs)

    dag = Dag(inputs)

    # Return the slurm submit script if the scheduler is slurm
    if settings.scheduler == EScheduler.SLURM:
        _slurm = SubmitSLURM(dag)
        slurm_script = str(Path(wk_dir) / _slurm.slurm_master_bash)
        return slurm_script

    # Return the path to the dag script if the scheduler is condor
    if settings.scheduler == EScheduler.CONDOR:
        # Adapted from https://github.com/jrbourbeau/pycondor/blob/master/pycondor/dagman.py#L286
        return os.path.join(str(Path(wk_dir) / dag.submit_directory), f'{dag.dag_name}.submit')

    return None


def write_ini_file(args, wk_dir):
    """
    Takes the parser args and writes the complete ini file in the job output directory

    :param args: Args as generated by the bilby_pipe parser
    :return: The updated Args, and the MainInput object representing the complete bilby_pipe input object
    """
    # Create an argument parser
    parser = create_parser()

    # Because we don't know the correct ini file name yet, we need to save the ini data to a temporary file
    # and then read the data back in to create a MainInput object, which we can then use to get the name of the ini
    # file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        parser.write_to_file(f.name, args, overwrite=True)

        # Make sure the data is flushed
        f.flush()

        # Read the data from the ini file
        args, unknown_args = parse_args([f.name], parser)

        # Generate the Input object so that we can determine the correct ini file
        # Working directory changes need to be synchronous
        with chdir_lock, set_directory(wk_dir):
            inputs = MainInput(args, unknown_args)

    # Write the real ini file
    parser.write_to_file(str(Path(wk_dir) / inputs.complete_ini_file), args, overwrite=True)

    return args, inputs


def create_working_directory(details):
    """
    Creates the working directory for the job. ie the output directory
    :param details: The job details provided by the client
    :return: The working (output) directory for the job
    """
    # Get the working directory
    wk_dir = Path(working_directory(details))

    # Create the working directory
    wk_dir.mkdir(parents=True, exist_ok=True)

    return str(wk_dir)


def submit(details, job_parameters):
    print("Submitting new job...")

    # Create and enter the working directory
    wk_dir = create_working_directory(details)

    # Get the ini ready for job submission
    args = prepare_ini_data(job_parameters, wk_dir)

    # Write the updated ini file
    args, inputs = write_ini_file(args, wk_dir)

    # Generate the submission scripts
    submission_script = write_submission_scripts(inputs, wk_dir)

    # If the job is open, we need to run the data generation step on the head nodes (ozstar specific) because compute
    # nodes do not have internet access. This is only applicable for slurm on ozstar
    if (not args.gaussian_noise or args.n_simulation == 0) and settings.scheduler == EScheduler.SLURM:
        # Process the slurm scripts to remove the data generation step
        data_gen_command = refactor_slurm_data_generation_step(submission_script)

        # Run the data generation step now
        run_data_generation(data_gen_command, wk_dir)

    # Actually submit the job
    sched = get_scheduler()

    # Working directory changes need to be synchronous
    with chdir_lock, set_directory(wk_dir):
        submit_bash_id = sched.submit(submission_script, wk_dir)

    # If the job was not submitted, simply return. When the job controller does a status update, we'll detect that
    # the job doesn't exist and report an error
    if not submit_bash_id:
        return None

    # Create a new job to store details
    job = {
        'job_id': get_next_unique_job_id(),
        'submit_id': submit_bash_id,
        'working_directory': wk_dir,
        'submit_directory': inputs.submit_directory
    }

    # Save the job in the database
    create_or_update_job(job)

    # return the job id
    return job['job_id']
