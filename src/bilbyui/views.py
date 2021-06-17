from tempfile import NamedTemporaryFile

from bilby_pipe.parser import create_parser
from bilby_pipe.data_generation import DataGenerationInput

from .models import BilbyJob, Label
from .utils.ini_utils import bilby_args_to_ini_string, bilby_ini_string_to_args
from .utils.jobs.submit_job import submit_job


def create_bilby_job(user, params):
    # First check the ligo permissions and ligo job status
    is_ligo_job = False

    # Check that non-ligo users only have access to GWOSC channels for real data
    # Note that we're checking for not simulated here, rather than for real, because the backend
    # explicitly checks for `if input_params["data"]["type"] == "simulated":`, so any value other than
    # `simulation` would result in a real data job
    if params.data.data_choice != "simulated" and (
            params.data.channels.hanford_channel != "GWOSC" or
            params.data.channels.livingston_channel != "GWOSC" or
            params.data.channels.virgo_channel != "GWOSC"
    ):
        # This is a real job, with a channel that is not GWOSC
        if not user.is_ligo:
            # User is not a ligo user, so they may not submit this job
            raise Exception("Non-LIGO members may only run real jobs on GWOSC channels")
        else:
            # User is a ligo user, so they may submit the job, but we need to track that the job is a
            # ligo "proprietary" job
            is_ligo_job = True

    # todo: request_cpus

    # Generate the detector choice
    detectors = []
    maximum_frequencies = {}
    minimum_frequencies = {}
    channels = {}
    for k, v in {
        ('hanford', 'H1'),
        ('livingston', 'L1'),
        ('virgo', 'V1')
    }:
        if getattr(params.detector, k):
            detectors.append(v)
            maximum_frequencies[v] = str(getattr(params.detector, k + "_maximum_frequency"))
            minimum_frequencies[v] = str(getattr(params.detector, k + "_minimum_frequency"))
            channels[v] = getattr(params.data.channels, k + "_channel")

    # Set the run type as simulation if required
    num_simulated = 0
    gaussian_noise = False
    if params.data.data_choice == "simulated":
        num_simulated = 1
        gaussian_noise = True

    # Set the waveform generator (Always fall back to BBH if invalid parameter provided)
    frequency_domain_source_model = "lal_binary_black_hole"
    if params.waveform.model == "binaryNeutronStar":
        frequency_domain_source_model = "lal_binary_neutron_star"

    sampler_kwargs = {
        'nlive': params.sampler.nlive,
        'nact': params.sampler.nact,
        'maxmcmc': params.sampler.maxmcmc,
        'walks': params.sampler.walks,
        'dlogz': str(params.sampler.dlogz)
    }

    # Parse the input parameters in to an argument dict
    data = {
        ################################################################################
        # Calibration arguments
        # Which calibration model and settings to use.
        ################################################################################

        ################################################################################
        # Data generation arguments
        # How to generate the data, e.g., from a list of gps times or simulated Gaussian noise.
        ################################################################################

        # The trigger time
        "trigger-time": params.data.trigger_time or "None",

        # If true, use simulated Gaussian noise
        "gaussian-noise": gaussian_noise,

        # Number of simulated segments to use with gaussian-noise Note, this must match the number of injections
        # specified
        "n-simulation": num_simulated,

        # Channel dictionary: keys relate to the detector with values the channel name, e.g. 'GDS-CALIB_STRAIN'.
        # For GWOSC open data, set the channel-dict keys to 'GWOSC'. Note, the dictionary should follow basic python
        # dict syntax.
        "channel-dict": repr(channels),

        ################################################################################
        # Detector arguments
        # How to set up the interferometers and power spectral density.
        ################################################################################

        # The names of detectors to use. If given in the ini file, detectors are specified by `detectors=[H1, L1]`. If
        # given at the command line, as `--detectors H1 --detectors L1`
        "detectors": repr(detectors),

        # The duration of data around the event to use
        "duration": params.detector.duration,

        # None
        "sampling-frequency": params.detector.sampling_frequency,

        # The maximum frequency, given either as a float for all detectors or as a dictionary (see minimum-frequency)
        "maximum-frequency": repr(maximum_frequencies),

        # The minimum frequency, given either as a float for all detectors or as a dictionary where all keys relate
        # the detector with values of the minimum frequency, e.g. {H1: 10, L1: 20}. If the waveform generation should
        # start the minimum frequency for any of the detectors, add another entry to the dictionary,
        # e.g., {H1: 40, L1: 60, waveform: 20}.
        "minimum-frequency": repr(minimum_frequencies),

        ################################################################################
        # Injection arguments
        # Whether to include software injections and how to generate them.
        ################################################################################

        ################################################################################
        # Job submission arguments
        # How the jobs should be formatted, e.g., which job scheduler to use.
        ################################################################################

        # Output label
        "label": params.details.name,

        # Use multi-processing. This options sets the number of cores to request. To use a pool of 8 threads on an
        # 8-core CPU, set request-cpus=8. For the dynesty, ptemcee, cpnest, and bilby_mcmc samplers, no additional
        # sampler-kwargs are required
        "request-cpus": params.sampler.cpus,

        # Some parameters set by job controller client

        ################################################################################
        # Likelihood arguments
        # Options for setting up the likelihood.
        ################################################################################

        ################################################################################
        # Output arguments
        # What kind of output/summary to generate.
        ################################################################################

        # Some parameters set by job controller client

        ################################################################################
        # Prior arguments
        # Specify the prior settings.
        ################################################################################

        # The prior file
        "prior-file": params.prior.prior_default,

        ################################################################################
        # Post processing arguments
        # What post-processing to perform.
        ################################################################################

        ################################################################################
        # Sampler arguments
        # None
        ################################################################################

        # Sampler to use
        "sampler": params.sampler.sampler_choice,

        # Dictionary of sampler-kwargs to pass in, e.g., {nlive: 1000} OR pass pre-defined set of sampler-kwargs
        # {Default, FastTest}
        "sampler-kwargs": repr(sampler_kwargs),

        ################################################################################
        # Waveform arguments
        # Setting for the waveform generator
        ################################################################################

        # Turns on waveform error catching
        "catch-waveform-errors": True,

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
    # injection_parameters.update(input_params['signal'])

    # Set the injection dict
    # data['injection'] = True
    # data['injection-dict'] = repr(injection_parameters)

    # priors = ""
    # for k, v in input_params["priors"].items():
    #     if v["type"] == "fixed":
    #         priors += f"{k} = {v['value']}\n" # f"{k} =
    #         Constraint(name='{k}', minimum={v['value']}, maximum={v['value']}),\n"
    #     elif v["type"] == "uniform":
    #         if "boundary" in v:
    #             priors += f"{k} =
    #             Uniform(name='{k}', minimum={v['min']}, maximum={v['max']}, boundary=\"{v['boundary']}\")\n"
    #         else:
    #             priors += f"{k} = Uniform(name='{k}', minimum={v['min']}, maximum={v['max']})\n"
    #     elif v["type"] == "sine":
    #         if "boundary" in v:
    #             priors += f"{k} = Sine(name='{k}', boundary=\"{v['boundary']}\")\n"
    #         else:
    #             priors += f"{k} = Sine(name='{k}')\n"
    #     else:
    #         print("Got unknown prior type", k, v)

    # Create an argument parser
    parser = create_parser()

    # Because we don't know the correct ini file name yet, we need to save the ini data to a temporary file
    # and then read the data back in to create a MainInput object, which we can then use to get the name of the ini
    # file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        parser.write_to_file(f.name, data, overwrite=True)

        # Make sure the data is flushed
        f.flush()

        ini_string = f.read().decode('utf-8')

    bilby_job = BilbyJob.objects.create(
        user_id=user.user_id,
        name=params.details.name,
        description=params.details.description,
        private=params.details.private,
        is_ligo_job=is_ligo_job,
        ini_string=ini_string
    )

    # Submit the job to the job controller

    # Create the parameter json
    params = bilby_job.as_json()

    result = submit_job(user, params)

    # Save the job id
    bilby_job.job_controller_id = result["jobId"]
    bilby_job.save()

    return bilby_job


def create_bilby_job_from_ini_string(user, params):
    # Parse the job ini file and create a bilby input class that can be used to read values from the ini
    args = bilby_ini_string_to_args(params.ini_string.ini_string.encode('utf-8'))
    args.idx = None
    args.ini = None

    if args.outdir == '.':
        args.outdir = "./"

    parser = DataGenerationInput(args, [], create_data=False)

    if args.n_simulation == 0 and (any([channel != 'GWOSC' for channel in (parser.channel_dict or {}).values()])):
        # This is a real job, with a channel that is not GWOSC
        if not user.is_ligo:
            # User is not a ligo user, so they may not submit this job
            raise Exception("Non-LIGO members may only run real jobs on GWOSC channels")
        else:
            is_ligo_job = True
    else:
        is_ligo_job = False

    # Override any required fields
    args.label = params.details.name

    # Convert the modified arguments back to an ini string
    ini_string = bilby_args_to_ini_string(args)

    bilby_job = BilbyJob(
        user_id=user.user_id,
        name=params.details.name,
        description=params.details.description,
        private=params.details.private,
        ini_string=ini_string,
        is_ligo_job=is_ligo_job
    )
    bilby_job.save()

    # Submit the job to the job controller

    # Create the parameter json
    params = bilby_job.as_json()

    result = submit_job(user, params)

    # Save the job id
    bilby_job.job_controller_id = result["jobId"]
    bilby_job.save()

    return bilby_job


def update_bilby_job(job_id, user, private=None, labels=None):
    bilby_job = BilbyJob.get_by_id(job_id, user)

    if user.user_id == bilby_job.user_id:
        if labels is not None:
            # Preserve protected labels
            protected_labels = bilby_job.labels.filter(protected=True)
            bilby_job.labels.set(Label.filter_by_name(labels) | protected_labels)

        if private is not None:
            bilby_job.private = private

        bilby_job.save()

        return 'Job saved!'
    else:
        raise Exception('You must own the job to change the privacy!')
