import json
import os
import subprocess
from tempfile import NamedTemporaryFile

import bilby_pipe.parser
from bilby_pipe.main import MainInput, generate_dag, Dag
from bilby_pipe.slurm import SubmitSLURM
from bilby_pipe.utils import parse_args

from core.misc import working_directory
from db import get_unique_job_id, update_job
from scheduler.slurm import slurm_submit
from settings import scheduler_env, scheduler


def submit(details, input_params):
    print("Submitting new job...")

    # Convert the job data to a json object
    input_params = json.loads(input_params)

    # Generate the detector choice
    detectors = []
    maximum_frequencies = {}
    minimum_frequencies = {}
    channels = {}
    for k, v in {
        'hanford': 'H1',
        'livingston': 'L1',
        'virgo': 'V1'
    }.items():
        if input_params["data"][k] == "True":
            detectors.append(v)
            maximum_frequencies[v] = input_params["data"][k + "_maximum_frequency"]
            minimum_frequencies[v] = input_params["data"][k + "_minimum_frequency"]
            channels[v] = input_params["data"][k + "_channel"]

    # Set the run type as simulation if required
    num_simulated = 0
    gaussian_noise = False
    if input_params["data"]["type"] == "simulation":
        num_simulated = 1
        gaussian_noise = True

    # Set the waveform generator (Always fall back to BBH if invalid parameter provided)
    frequency_domain_source_model = "lal_binary_black_hole"
    if input_params["signal"]["model"] == "binaryNeutronStar":
        frequency_domain_source_model = "lal_binary_neutron_star"

    # Parse the json file and set simple parameters
    data = {
        ################################################################################
        ## Calibration arguments
        # Which calibration model and settings to use.
        ################################################################################

        ################################################################################
        ## Data generation arguments
        # How to generate the data, e.g., from a list of gps times or simulated Gaussian noise.
        ################################################################################

        # The trigger time
        "trigger-time": input_params["data"]["trigger_time"] if len(input_params["data"]["trigger_time"]) else "None",

        # If true, use simulated Gaussian noise
        "gaussian-noise": gaussian_noise,

        # Number of simulated segments to use with gaussian-noise Note, this must match the number of injections specified
        "n-simulation": num_simulated,

        # Channel dictionary: keys relate to the detector with values the channel name, e.g. 'GDS-CALIB_STRAIN'. For GWOSC open data, set the channel-dict keys to 'GWOSC'. Note, the dictionary should follow basic python dict syntax.
        "channel-dict": repr(channels),

        ################################################################################
        ## Detector arguments
        # How to set up the interferometers and power spectral density.
        ################################################################################

        # The names of detectors to use. If given in the ini file, detectors are specified by `detectors=[H1, L1]`. If
        # given at the command line, as `--detectors H1 --detectors L1`
        "detectors": repr(detectors),

        # The duration of data around the event to use
        "duration": input_params["data"]["signal_duration"],

        # None
        "sampling-frequency": input_params["data"]["sampling_frequency"],

        # The maximum frequency, given either as a float for all detectors or as a dictionary (see minimum-frequency)
        "maximum-frequency": repr(maximum_frequencies),

        # The minimum frequency, given either as a float for all detectors or as a dictionary where all keys relate the detector with values of the minimum frequency, e.g. {H1: 10, L1: 20}. If the waveform generation should start the minimum frequency for any of the detectors, add another entry to the dictionary, e.g., {H1: 40, L1: 60, waveform: 20}.
        "minimum-frequency": repr(minimum_frequencies),

        ################################################################################
        ## Injection arguments
        # Whether to include software injections and how to generate them.
        ################################################################################

        ################################################################################
        ## Job submission arguments
        # How the jobs should be formatted, e.g., which job scheduler to use.
        ################################################################################

        # Output label
        "label": input_params["name"],

        # Format submission script for specified scheduler. Currently implemented: SLURM
        "scheduler": scheduler,

        # Environment scheduler sources during runtime
        "scheduler_env": scheduler_env,

        ################################################################################
        ## Likelihood arguments
        # Options for setting up the likelihood.
        ################################################################################

        ################################################################################
        ## Output arguments
        # What kind of output/summary to generate.
        ################################################################################

        # Create diagnostic and posterior plots
        "create-plots": True,

        # Create calibration posterior plot
        "plot-calibration": False,

        # Create intrinsic and extrinsic posterior corner plots
        "plot-corner": True,

        # Create 1-d marginal posterior plots
        "plot-marginal": True,

        # Create posterior skymap
        "plot-skymap": True,

        # Create waveform posterior plot
        "plot-waveform": True,

        # Format for making bilby_pipe plots, can be [png, pdf, html]. If specified format is not supported, will
        # default to png.
        "plot-format": "png",

        # Create a PESummary page
        "create-summary": False,

        ################################################################################
        ## Prior arguments
        # Specify the prior settings.
        ################################################################################

        # The prior file
        "prior-file": input_params["priors"]["default"],

        ################################################################################
        ## Post processing arguments
        # What post-processing to perform.
        ################################################################################

        ################################################################################
        ## Sampler arguments
        # None
        ################################################################################

        # Sampler to use
        "sampler": input_params["sampler"]["type"],

        ################################################################################
        ## Waveform arguments
        # Setting for the waveform generator
        ################################################################################

        # Name of the frequency domain source model. Can be one of[lal_binary_black_hole, lal_binary_neutron_star,
        # lal_eccentric_binary_black_hole_no_spins, sinegaussian, supernova, supernova_pca_model] or any python path
        # to a bilby  source function the users installation, e.g. examp.source.bbh
        "frequency-domain-source-model": frequency_domain_source_model
    }


    # Sets up some default parameters
    # injection_parameters = dict(
    #     chirp_mass=35, mass_ratio=1, a_1=0.0, a_2=0.0, tilt_1=0.0, tilt_2=0.0,
    #     phi_12=0.0, phi_jl=0.0, luminosity_distance=2000., theta_jn=0.5, psi=0.24,
    #     phase=1.3, geocent_time=0, ra=1.375, dec=-1.2108)

    # Overwrite the defaults with those from the job (eventually should just use the input)
    #injection_parameters.update(input_params['signal'])

    # Set the injection dict
    #data['injection'] = True
    #data['injection-dict'] = repr(injection_parameters)

    # priors = ""
    # for k, v in input_params["priors"].items():
    #     if v["type"] == "fixed":
    #         priors += f"{k} = {v['value']}\n" # f"{k} = Constraint(name='{k}', minimum={v['value']}, maximum={v['value']}),\n"
    #     elif v["type"] == "uniform":
    #         if "boundary" in v:
    #             priors += f"{k} = Uniform(name='{k}', minimum={v['min']}, maximum={v['max']}, boundary=\"{v['boundary']}\")\n"
    #         else:
    #             priors += f"{k} = Uniform(name='{k}', minimum={v['min']}, maximum={v['max']})\n"
    #     elif v["type"] == "sine":
    #         if "boundary" in v:
    #             priors += f"{k} = Sine(name='{k}', boundary=\"{v['boundary']}\")\n"
    #         else:
    #             priors += f"{k} = Sine(name='{k}')\n"
    #     else:
    #         print("Got unknown prior type", k, v)


    # Get the working directory
    wk_dir = working_directory(details, input_params)

    # Create the working directory
    os.makedirs(wk_dir, exist_ok=True)

    # Change to the working directory
    os.chdir(wk_dir)

    # Create an argument parser
    parser = bilby_pipe.parser.create_parser()

    # Because we don't know the correct ini file name yet, we need to save the ini data to a temporary file
    # and then read the data back in to create a MainInput object, which we can then use to get the name of the ini
    # file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        parser.write_to_file(f.name, data, overwrite=True)

        # Read the data from the ini file
        args, unknown_args = parse_args([f.name], parser)

        # Generate the Input object so that we can determine the correct ini file
        inputs = MainInput(args, unknown_args)

    # Write the real ini file
    parser.write_to_file(inputs.complete_ini_file, data, overwrite=True)

    # Generate the submission scripts
    generate_dag(inputs)

    # Get the name of the slurm script
    dag = Dag(inputs)
    _slurm = SubmitSLURM(dag)
    slurm_script = _slurm.slurm_master_bash

    # If the job is open, we need to run the data generation step on the head nodes (ozstar specific) because compute
    # nodes do not have internet access.
    if not gaussian_noise or num_simulated == 0:
        # Read the lines from the submit script
        slines = open(slurm_script, 'r').readlines()

        # Find the line for data generation and the first echo after that, then remove the dependency from the following
        # sbatch command
        data_gen_idx = None
        data_gen_command = None
        new_lines = []
        generation_jid = None
        echo_found = False
        for index in range(len(slines)):
            line = slines[index]

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

        # Write the updated lines to the job submission script
        with open(slurm_script, 'w') as f:
            f.write(''.join(new_lines))

        # Now manually run the data generation (This bundle is running on the login nodes)
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

        # Run the data generation
        p = subprocess.Popen(
            f'bash {os.path.abspath(os.path.join(wk_dir, data_gen_command))}',
            cwd=wk_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        p.wait()

        # Get the output from the data generation command
        stdout, stderr = p.communicate()

        # Write the data generation output to output files
        with open(output_file, "w") as f:
            f.write(stdout.decode())

        with open(error_file, "w") as f:
            f.write(stderr.decode())

    # Actually submit the job
    submit_bash_id = slurm_submit(slurm_script, wk_dir)

    # If the job was not submitted, simply return. When the job controller does a status update, we'll detect that
    # the job doesn't exist and report an error
    if not submit_bash_id:
        return None

    # Create a new job to store details
    job = {
        'job_id': get_unique_job_id(),
        'submit_id': submit_bash_id,
        'working_directory': wk_dir,
        'submit_directory': inputs.submit_directory
    }

    # Save the job in the database
    update_job(job)

    # return the job id
    return job['job_id']
