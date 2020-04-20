import json
import os
from tempfile import NamedTemporaryFile

import bilby_pipe.parser
from bilby_pipe.main import MainInput, generate_dag, Dag
from bilby_pipe.slurm import SubmitSLURM
from bilby_pipe.utils import parse_args

from core.misc import working_directory
from db import get_unique_job_id, update_job
from scheduler.slurm import slurm_submit


def submit(details, job_data):
    print("Submitting new job...")

    # Convert the job data to a json object
    job_data = json.loads(job_data)

    # Parse the json file
    data = {}
    data["label"] = job_data["name"]
    data["detectors"] = job_data["data"]["detector_choice"]
    data["duration"] = job_data["data"]["signal_duration"]
    data["sampling-frequency"] = job_data["data"]["sampling_frequency"]
    data["trigger-time"] = job_data["data"]["start_time"]

    # Sets up some default parameters
    injection_parameters = dict(
        chirp_mass=35, mass_ratio=1, a_1=0.0, a_2=0.0, tilt_1=0.0, tilt_2=0.0,
        phi_12=0.0, phi_jl=0.0, luminosity_distance=2000., theta_jn=0.5, psi=0.24,
        phase=1.3, geocent_time=0, ra=1.375, dec=-1.2108)

    # Overwrite the defaults with those from the job (eventually should just use the input)
    injection_parameters.update(job_data['signal'])

    # Set the injection dict
    data['injection'] = True
    data['injection-dict'] = repr(injection_parameters)

    priors = ""
    for k, v in job_data["priors"].items():
        if v["type"] == "fixed":
            priors += f"{k} = {v['value']}\n" # f"{k} = Constraint(name='{k}', minimum={v['value']}, maximum={v['value']}),\n"
        elif v["type"] == "uniform":
            if "boundary" in v:
                priors += f"{k} = Uniform(name='{k}', minimum={v['min']}, maximum={v['max']}, boundary=\"{v['boundary']}\")\n"
            else:
                priors += f"{k} = Uniform(name='{k}', minimum={v['min']}, maximum={v['max']})\n"
        elif v["type"] == "sine":
            if "boundary" in v:
                priors += f"{k} = Sine(name='{k}', boundary=\"{v['boundary']}\")\n"
            else:
                priors += f"{k} = Sine(name='{k}')\n"
        else:
            print("Got unknown prior type", k, v)

    data["prior-dict"] = "{\n" + priors + "}"

    data["sampler"] = job_data["sampler"]["type"]
    sampler_data = job_data["sampler"]
    del sampler_data["type"]

    data["sampler-kwargs"] = repr(sampler_data)

    data["create-plots"] = True
    data["plot-calibration"] = False
    data["plot-corner"] = True
    data["plot-marginal"] = True
    data["plot-skymap"] = True
    data["plot-waveform"] = True
    data["plot-form"] = True
    data["create-summary"] = False

    # Set the run type as simulation
    data["n-simulation"] = 1
    data["gaussian-noise"] = True

    # Set the scheduler
    data["scheduler"] = "slurm"

    # ???
    data["phase-marginalization"] = True
    data["time-marginalization"] = True
    data["jitter-time"] = False

    data["scheduler_env"] = "/home/lewis/Projects/gwcloud_bilby/src/bundle/venv/bin/activate"

    # Get the working directory
    wk_dir = working_directory(details, job_data)

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