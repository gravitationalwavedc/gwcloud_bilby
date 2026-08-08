import hashlib
import json
import logging
import shutil
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import bilby_pipe
from adacs_sso_plugin.models import APISessionToken
from bilby_pipe.data_generation import DataGenerationInput
from bilby_pipe.parser import create_parser
from bilby_pipe.utils import convert_string_to_dict
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.views.decorators.http import require_GET, require_POST
from graphql import GraphQLError
from graphql_relay.node.node import from_global_id, to_global_id
from gwosc.datasets import event_gps

from .constants import BilbyJobType
from .models import (
    BilbyJob,
    EventID,
    ExternalBilbyJob,
    FileDownloadToken,
    GWFlowFile,
    GWFlowJob,
    Label,
    SupportingFile,
)
from .services.api_tokens import create_token, list_tokens, revoke_token, serialize_token
from .services.event_ids import get_event_id, list_event_ids_for_user
from .services.jobs import get_job, list_public_jobs, list_user_jobs, update_job
from .status import JobStatus
from .types import GWFlowPendingFile
from .utils.embargo import should_embargo_job
from .utils.gen_parameter_output import generate_parameter_output
from .utils.gwflow_es import gwflow_elastic_search_update
from .utils.gwflow_es import update_child_job_ids as update_gwflow_child_job_ids
from .utils.ini_utils import bilby_args_to_ini_string, bilby_ini_string_to_args
from .utils.job_ref import resolve_job_ref_view
from .utils.job_validation import validate_job_name
from .utils.jobs.request_file_download_id import request_file_download_ids
from .utils.jobs.request_job_filter import request_job_filter
from .utils.misc import is_ligo_user

logger = logging.getLogger(__name__)

STATUS_BADGE_CLASSES = {
    "Completed": "primary",
    "Error": "danger",
    "Running": "info",
    "Unknown": "dark",
}


def check_job_embargo_status(user, args):
    """
    Check if a job should be embargoed based on user and job arguments.

    This function serves two distinct purposes depending on the context:

    1. UPLOAD PERMISSION CHECK (when user is the actual uploader):
       - Used in upload functions (upload_bilby_job, upload_external_bilby_job, upload_hdf5_bilby_job)
       - Determines if the current user is allowed to upload this specific job
       - LIGO users can upload embargoed jobs, non-LIGO users cannot
       - Throws exception if non-LIGO user tries to upload embargoed data

    2. JOB CLASSIFICATION CHECK (when user is None):
       - Used in _create_bilby_job_record to determine the is_ligo_job flag
       - Simulates a non-LIGO user to determine if the job contains proprietary LIGO data
       - If the job would be embargoed for a non-LIGO user, it contains LIGO data
       - This flag controls job visibility: non-LIGO users can't see LIGO data jobs

    The embargo logic considers:
    - trigger_time: Jobs with trigger_time >= EMBARGO_START_TIME are embargoed
    - n_simulation: Simulated jobs (n_simulation != 0) are never embargoed
    - user status: LIGO users bypass embargo restrictions

    Args:
        user: The user object. If None, treats as non-LIGO user for embargo checking.
        args: Parsed INI arguments containing trigger_time and n_simulation

    Returns:
        bool: True if the job should be embargoed, False otherwise.
    """
    # Parse trigger_time from INI args - can be a float or event name like "GW150914"
    try:
        trigger_time = float(args.trigger_time)
    except ValueError:  # If trigger time is not able to be converted to a float
        try:
            trigger_time = event_gps(args.trigger_time)  # Try to resolve event name to GPS time
        except ValueError:  # If event_gps cannot find the event, raises a ValueError
            trigger_time = None
    except TypeError:
        trigger_time = None

    # Parse n_simulation from INI args - determines if job uses simulated data
    n_simulation = args.n_simulation
    # Convert to boolean for embargo checking (0 = False, non-zero = True)
    if n_simulation is not None:
        n_simulation = bool(int(n_simulation))

    # Delegate to the core embargo logic in utils/embargo.py
    return should_embargo_job(user, trigger_time, n_simulation)


def _parse_and_validate_ini(ini_content):
    """Parse INI content and return validated args."""
    args = bilby_ini_string_to_args(ini_content.encode("utf-8"))
    validate_job_name(args.label)
    return args


def _create_bilby_job_record(user, details, args, job_type, ini_string=None):
    """Create a BilbyJob record with common logic."""
    if ini_string is None:
        ini_string = bilby_args_to_ini_string(args)

    # Check if this job would be embargoed for non-LIGO users.
    # If so, it contains proprietary LIGO data and should be marked as a LIGO job.
    # We pass None as the user parameter to simulate a non-LIGO user, which allows us
    # to determine if the job contains embargoed data regardless of who is actually uploading it.
    is_ligo_job = check_job_embargo_status(None, args)

    bilby_job = BilbyJob.objects.create(
        user=user,
        name=args.label,
        description=details.description,
        private=details.private,
        ini_string=ini_string,
        job_type=job_type,
        is_ligo_job=is_ligo_job,
    )

    # Set official label for GWOSC ingest user
    if user.id == settings.GWOSC_INGEST_USER:
        bilby_job.labels.set([Label.objects.get(name="Official")])

    return bilby_job


def create_bilby_job(user, params):
    logger.info("User %s creating Bilby job: %s", user.id, params.details.name)

    if should_embargo_job(user, float(params.data.trigger_time), params.data.data_choice == "simulated"):
        logger.warning("User %s attempted to run real job on embargoed data: %s", user.id, params.details.name)
        msg = "Only LIGO users may run real jobs on embargoed LIGO data"
        raise Exception(msg)

    validate_job_name(params.details.name)

    # Check the ligo permissions and ligo job status
    is_ligo_job = False

    # todo: request_cpus

    # Generate the detector choice
    detectors = []
    maximum_frequencies = {}
    minimum_frequencies = {}
    channels = {}
    for k, v in [("hanford", "H1"), ("livingston", "L1"), ("virgo", "V1")]:
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
        "nlive": params.sampler.nlive,
        "nact": params.sampler.nact,
        "maxmcmc": params.sampler.maxmcmc,
        "walks": params.sampler.walks,
        "dlogz": str(params.sampler.dlogz),
    }

    # Parse the input parameters into an argument dict
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
        "frequency-domain-source-model": frequency_domain_source_model,
    }

    # Create an argument parser
    parser = create_parser()

    # Because we don't know the correct ini file name yet, we need to save the ini data to a temporary file
    # and then read the data back into create a MainInput object, which we can then use to get the name of the ini
    # file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        parser.write_to_file(f.name, data, overwrite=True)

        # Make sure the data is flushed
        f.flush()

        ini_string = f.read().decode("utf-8")

    event_id = EventID.get_by_event_id(params.data.event_id, user) if params.data.event_id else None

    try:
        bilby_job = BilbyJob.objects.create(
            user=user,
            name=params.details.name,
            description=params.details.description,
            private=params.details.private,
            is_ligo_job=is_ligo_job,
            ini_string=ini_string,
            cluster=params.details.cluster,
            event_id=event_id,
        )
        logger.info("Created Bilby job %s for user %s", bilby_job.id, user.id)

        # Submit the job to the job controller
        bilby_job.submit()
        logger.info("Successfully submitted job %s to job controller", bilby_job.id)
    except ValueError:
        logger.exception("Failed to create/submit job for user %s", user.id)
        raise
    else:
        return bilby_job


def parse_supporting_files(parser, args, prior_file, gps_file, timeslide_file, injection_file, psd_dict):
    """
    Given a DataGenerationInput object, parser, this function will generate a dictionary representing any supporting
    files from the input, and then remove those supporting files from the parser. The other parameter is a
    BilbyArgParser instance which will also have the supporting file removed from.
    """
    supporting_files = {}

    if prior_file:
        supporting_files[SupportingFile.PRIOR] = prior_file

    if gps_file:
        supporting_files[SupportingFile.GPS] = gps_file

    if timeslide_file:
        supporting_files[SupportingFile.TIME_SLIDE] = timeslide_file

    if injection_file:
        supporting_files[SupportingFile.INJECTION] = injection_file

    for supporting_file_type, config_name in {
        SupportingFile.PSD: "psd_dict",
        SupportingFile.CALIBRATION: "spline_calibration_envelope_dict",
        SupportingFile.NUMERICAL_RELATIVITY: "numerical_relativity_file",
        SupportingFile.DISTANCE_MARGINALIZATION_LOOKUP_TABLE: "distance_marginalization_lookup_table",
        SupportingFile.DATA: "data_dict",
    }.items():
        if config_name == "psd_dict":
            if not psd_dict:
                continue

            config = convert_string_to_dict(psd_dict, "psd-dict")
        elif config_name == "distance_marginalization_lookup_table":
            # Bilby pipe has a weird way to deal with default distance marginalisation tables. If the distance
            # marginalisation lookup table is None, then bilby_pipe will copy a default one for the specified prior
            # into the current working directory. Then upon our code trying to check if that file exists, we get an
            # error. Instead, we need to check if the provided marginalisation lookup table is one of the defaults, and
            # ignore it if it is. See get_distance_file_lookup_table() in
            # https://git.ligo.org/lscsoft/bilby_pipe/-/blob/master/bilby_pipe/input.py#L781
            # From bilby_pipe 1.8+, DataGenerationInput may not expose this attribute; read from args if needed.
            config = getattr(parser, config_name, None) or getattr(args, config_name, None)
            if config is None:
                continue

            # Get the path to the marginalisation file. If the filename begins with ".", then assume that
            # the distance marginalisation isn't provided and is a default. For a default marginalisation file, the path
            # will be something like `outdir/.4s_distance_marginalization_lookup.npz`
            path = Path(config)
            if path.name[0] == ".":
                # Here we continue, since there is no reason to create a SupportingFile record for default
                # marginalisation files.
                continue
        else:
            # Check if this configuration parameter is set in the parser or args (args is the argparse namespace;
            # parser is DataGenerationInput and may not expose all attributes in newer bilby_pipe).
            config = getattr(parser, config_name, None) or getattr(args, config_name, None)
            if config is None:
                continue

        if isinstance(config, dict):
            # Handle this configuration item as a dictionary of files
            # ie. {'L1': './supporting_files/psd/L1-psd.dat', 'V1': './supporting_files/psd/V1-psd.dat'}
            supporting_files.setdefault(supporting_file_type, [])
            for k, f in config.items():
                supporting_files[supporting_file_type].append({k: f})

            # Clear this configuration item from the parser
            setattr(parser, config_name, None)
            setattr(args, config_name, None)

        elif isinstance(config, str):
            # This config item is a single file
            supporting_files.setdefault(supporting_file_type, config)

            # Clear this configuration item from the parser
            setattr(parser, config_name, None)
            setattr(args, config_name, None)

        else:
            logger.error("Got unknown supporting file type for %s: %s", config_name, config)

    return supporting_files


def bilby_ini_args_to_data_input(args):
    # Strip the prior, gps, timeslide, and injection file
    # as DataGenerationInput has trouble without the actual file existing
    # Don't change the prior file if it's one of the defaults
    args.gps_file = None
    args.timeslide_file = None
    args.injection_file = None
    args.psd_dict = None

    # DataGenerationInput expects args.idx; its generation_seed setter asserts idx is not None only when generation_seed is set
    args.idx = getattr(args, "idx", None)
    if getattr(args, "generation_seed", None) is not None and args.idx is None:
        args.idx = 0
    args.ini = None

    if args.prior_file not in bilby_pipe.main.Input([], []).default_prior_files:
        args.prior_file = None

    return DataGenerationInput(args, [], create_data=False)


def create_bilby_job_from_ini_string(user, params):
    is_ligo_job = False

    # Parse the job ini file and create a bilby input class that can be used to read values from the ini
    args = bilby_ini_string_to_args(params.ini_string.ini_string.encode("utf-8"))

    if check_job_embargo_status(user, args):
        msg = "Only LIGO users may run real jobs on embargoed LIGO data"
        raise Exception(msg)

    if args.outdir == ".":
        args.outdir = "./"

    # Get the files for any supporting files if they exist
    prior_file = None
    if args.prior_file not in bilby_pipe.main.Input([], []).default_prior_files:
        prior_file = args.prior_file

    gps_file = args.gps_file
    timeslide_file = args.timeslide_file
    injection_file = args.injection_file
    psd_dict = args.psd_dict

    parser = bilby_ini_args_to_data_input(args)

    # Parse any supporting files
    supporting_files = parse_supporting_files(
        parser, args, prior_file, gps_file, timeslide_file, injection_file, psd_dict
    )

    # Override any required fields
    validate_job_name(params.details.name)
    args.label = params.details.name

    # Convert the modified arguments back to an ini string
    ini_string = bilby_args_to_ini_string(args)

    bilby_job = BilbyJob(
        user=user,
        name=params.details.name,
        description=params.details.description,
        private=params.details.private,
        ini_string=ini_string,
        is_ligo_job=is_ligo_job,
        cluster=params.details.cluster,
    )
    bilby_job.save()

    # Save any supporting file records
    supporting_file_details = SupportingFile.save_from_parsed(bilby_job, supporting_files)

    # Submit the job to the job controller if there are no supporting files
    if not bilby_job.has_supporting_files():
        bilby_job.submit()

    return bilby_job, supporting_file_details


def update_bilby_job(job_id, user, private=None, labels=None, event_id=None, name=None, description=None):
    _, message = update_job(
        job_id,
        user,
        private=private,
        labels=labels,
        event_id=event_id,
        name=name,
        description=description,
    )
    return message


def upload_bilby_job(user, upload_token, details, job_file):
    logger.info("User %s uploading Bilby job: %s, file: %s", user.id, details.name, job_file.name)

    # Check that the uploaded file is a tar.gz file
    if not job_file.name.endswith("tar.gz"):
        logger.error("User %s attempted to upload non-tar.gz file: %s", user.id, job_file.name)
        msg = "Job upload should be a tar.gz file"
        raise ValueError(msg)

    # Check that the job upload directory exists
    Path(settings.JOB_UPLOAD_STAGING_DIR).mkdir(parents=True, exist_ok=True)

    # Write out the uploaded job to disk and unpack the archive to a temporary staging directory
    with (
        TemporaryDirectory(dir=settings.JOB_UPLOAD_STAGING_DIR) as job_staging_dir,
        NamedTemporaryFile(dir=settings.JOB_UPLOAD_STAGING_DIR, suffix=".tar.gz") as job_upload_file,
        UploadedFile(job_file) as django_job_file,
    ):
        # Write the uploaded file to the temporary file
        for c in django_job_file.chunks():
            job_upload_file.write(c)
        job_upload_file.flush()

        # Unpack the archive to the temporary directory
        p = subprocess.Popen(
            ["tar", "-xvf", job_upload_file.name, "."],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=job_staging_dir,
        )
        out, err = p.communicate()

        logger.info("Unpacking uploaded job archive %s had return code %s", job_file.name, p.returncode)
        logger.debug("stdout: %s", out)
        logger.debug("stderr: %s", err)

        if p.returncode != 0:
            msg = "Invalid or corrupt tar.gz file"
            raise ValueError(msg)

        # Validate the directory structure, this should include 'data', 'result', and 'results_page' at minimum
        for directory in ["data", "result", "results_page"]:
            if not (Path(job_staging_dir) / directory).is_dir():
                msg = f"Invalid directory structure, expected directory ./{directory} to exist."
                raise ValueError(msg)

        # Find the config complete ini
        ini_file = [
            x for x in Path(job_staging_dir).iterdir() if x.is_file() and x.name.endswith("_config_complete.ini")
        ]

        if len(ini_file) != 1:
            msg = "Invalid number of ini files ending in `_config_complete.ini`. There should be exactly one."
            raise ValueError(msg)

        ini_file = ini_file[0]

        # Read the ini file
        with (Path(job_staging_dir) / ini_file).open() as f:
            ini_content = f.read()

        # Parse and validate the INI file
        args = _parse_and_validate_ini(ini_content)

        # Validate embargo permissions - only LIGO users may upload real jobs on embargoed LIGO data
        if check_job_embargo_status(user, args):
            msg = "Only LIGO users may upload real jobs on embargoed LIGO data"
            raise PermissionError(msg)

        # DataGenerationInput expects args.idx; its generation_seed setter asserts idx is not None only when generation_seed is set
        args.idx = getattr(args, "idx", None)
        if getattr(args, "generation_seed", None) is not None and args.idx is None:
            args.idx = 0
        args.ini = None

        # Override the output directory - since in the supported directory structure the output is always relative to
        # the current working directory (root of the job)
        args.outdir = "./"

        # Strip the prior, gps, timeslide, and injection file
        # as DataGenerationInput has trouble without the actual file existing

        # Don't change the prior file if it's one of the defaults
        prior_file = None
        if args.prior_file not in bilby_pipe.main.Input([], []).default_prior_files:
            prior_file = args.prior_file
            args.prior_file = None

        gps_file = args.gps_file
        args.gps_file = None

        timeslide_file = args.timeslide_file
        args.timeslide_file = None

        injection_file = args.injection_file
        args.injection_file = None

        psd_dict = args.psd_dict
        args.psd_dict = None

        parser = DataGenerationInput(args, [], create_data=False)

        # Parse any supporting files
        supporting_files = parse_supporting_files(
            parser, args, prior_file, gps_file, timeslide_file, injection_file, psd_dict
        )

        # Convert the modified arguments back to an ini string
        ini_string = bilby_args_to_ini_string(args)

        with transaction.atomic():
            # This is in an atomic block in case:-
            # * The ini file somehow ends up broken
            # * The final move of the staging directory to the job directory raises an exception (Disk full etc)
            # * The generation of the archive.tar.gz file fails (Disk full etc)

            # Create the bilby job record
            bilby_job = _create_bilby_job_record(user, details, args, BilbyJobType.UPLOADED, ini_string)
            # Override the user_id to use the upload token's user
            bilby_job.user = upload_token.user
            bilby_job.save()

            # Save any supporting file records
            supporting_file_details = SupportingFile.save_from_parsed(bilby_job, supporting_files, uploaded=True)

            # Check that the job directory exists for this supporting file
            supporting_file_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(bilby_job.id)
            supporting_file_dir.mkdir(exist_ok=True, parents=True)

            # Make sure the source supporting file exists
            for supporting_file in supporting_file_details:
                source_file = Path(job_staging_dir) / supporting_file["file_path"]
                if not source_file.is_file():
                    msg = f"Supporting file {supporting_file['file_path']} does not exist."
                    raise FileNotFoundError(msg)

                # Because we're in a transaction here, the bulk_create in `SupportingFile.save_from_parsed` isn't saved
                # so we need to fetch it again from the database to get the inserted ID
                supporting_file_instance = SupportingFile.objects.get(download_token=supporting_file["download_token"])
                source_file = Path(job_staging_dir) / supporting_file["file_path"]
                shutil.copyfile(source_file, supporting_file_dir / str(supporting_file_instance.id))

            # Now we have the bilby job id, we can move the staging directory to the actual job directory
            job_dir = bilby_job.get_upload_directory()
            shutil.move(job_staging_dir, job_dir)

            # Finally generate the archive.tar.gz file
            p = subprocess.Popen(
                ["tar", "-cvf", "archive.tar.gz", "."],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=job_dir,
            )
            out, err = p.communicate()

            logger.info("Packing uploaded job archive for %s had return code %s", job_file.name, p.returncode)
            logger.debug("stdout: %s", out)
            logger.debug("stderr: %s", err)

            if p.returncode != 0:
                logger.error("Failed to repack uploaded job for user %s", user.id)
                msg = "Unable to repack the uploaded job"
                raise RuntimeError(msg)

        # Job is validated and uploaded, return the job
        logger.info("Successfully uploaded and created job %s for user %s", bilby_job.id, user.id)
        return bilby_job


def upload_external_bilby_job(user, details, ini_file, result_url):
    logger.info("User %s uploading external Bilby job: %s from %s", user.id, details.name, result_url)

    # Parse and validate the INI file
    args = _parse_and_validate_ini(ini_file)

    # Validate embargo permissions - only LIGO users may upload real jobs on embargoed LIGO data
    if check_job_embargo_status(user, args):
        logger.warning("User %s attempted to upload external job on embargoed data", user.id)
        msg = "Only LIGO users may upload real jobs on embargoed LIGO data"
        raise PermissionError(msg)

    # Set the job name from details
    args.label = details.name

    # Strip the prior, gps, timeslide, and injection file
    # as DataGenerationInput has trouble without the actual file existing
    # DataGenerationInput expects args.idx; its generation_seed setter asserts idx is not None only when generation_seed is set
    args.idx = getattr(args, "idx", None)
    if getattr(args, "generation_seed", None) is not None and args.idx is None:
        args.idx = 0
    args.ini = None

    # Don't change the prior file if it's one of the defaults
    if args.prior_file not in bilby_pipe.main.Input([], []).default_prior_files:
        args.prior_file = None

    args.gps_file = None
    args.timeslide_file = None
    args.injection_file = None
    args.psd_dict = None

    # Create the bilby job record
    bilby_job = _create_bilby_job_record(user, details, args, BilbyJobType.EXTERNAL)

    # Create the relevant External Bilby Job record as well
    ExternalBilbyJob.objects.create(job=bilby_job, url=result_url)

    logger.info("Successfully uploaded external job %s for user %s", bilby_job.id, user.id)
    return bilby_job


def upload_hdf5_bilby_job(user, upload_token, details, hdf5_file, ini_file):
    """
    Upload a bilby job with HDF5 result file and INI configuration file.

    This function creates an UPLOADED job type with the actual HDF5 result file
    and INI configuration file stored in GWCloud's internal storage.

    Args:
        user: The user uploading the job
        upload_token: The upload token for authentication
        details: Job details (name, description, private, etc.)
        hdf5_file: The HDF5 result file
        ini_file: The INI configuration file

    Returns:
        BilbyJob: The created bilby job
    """
    # Check that the uploaded files are the correct types
    if not hdf5_file.name.endswith((".hdf5", ".h5")):
        msg = "HDF5 file should have .hdf5 or .h5 extension"
        raise ValueError(msg)

    if not ini_file.name.endswith(".ini"):
        msg = "INI file should have .ini extension"
        raise ValueError(msg)

    # Check that the job upload directory exists
    Path(settings.JOB_UPLOAD_STAGING_DIR).mkdir(parents=True, exist_ok=True)

    # Create a temporary staging directory for the job
    with TemporaryDirectory(dir=settings.JOB_UPLOAD_STAGING_DIR) as job_staging_dir:
        # Create the required directory structure
        for directory in ["data", "result", "results_page"]:
            (Path(job_staging_dir) / directory).mkdir(parents=True, exist_ok=True)

        # Save the HDF5 file to the result directory
        hdf5_path = Path(job_staging_dir) / "result" / "result.hdf5"
        with hdf5_path.open("wb") as f:
            f.writelines(hdf5_file.chunks())

        # Save the INI file with the correct naming convention
        job_name = details.name
        ini_filename = f"{job_name}_config_complete.ini"
        ini_path = Path(job_staging_dir) / ini_filename
        with ini_path.open("wb") as f:
            f.writelines(ini_file.chunks())

        # Read and parse the INI file
        with ini_path.open() as f:
            ini_content = f.read()

        # Parse and validate the INI file
        args = _parse_and_validate_ini(ini_content)

        # Validate embargo permissions - only LIGO users may upload real jobs on embargoed LIGO data
        if check_job_embargo_status(user, args):
            msg = "Only LIGO users may upload real jobs on embargoed LIGO data"
            raise PermissionError(msg)

        # Override the output directory
        args.outdir = "./"

        # Strip the prior, gps, timeslide, and injection file
        # as DataGenerationInput has trouble without the actual file existing
        # For HDF5 uploads, these files don't actually exist as physical files

        # Don't change the prior file if it's one of the defaults
        if args.prior_file not in bilby_pipe.main.Input([], []).default_prior_files:
            args.prior_file = None

        args.gps_file = None
        args.timeslide_file = None
        args.injection_file = None
        args.psd_dict = None

        # TODO: Better handle supporting files for HDF5 uploads if it's even possible
        # For now, we skip supporting files since they don't exist as physical files
        # in HDF5 uploads - the data might be embedded in the HDF5 file itself?

        # Convert the modified arguments back to an ini string
        ini_string = bilby_args_to_ini_string(args)

        with transaction.atomic():
            # Create the bilby job record
            bilby_job = _create_bilby_job_record(user, details, args, BilbyJobType.UPLOADED, ini_string)
            # Override the user_id to use the upload token's user
            bilby_job.user = upload_token.user
            bilby_job.save()

            # Move the staging directory to the actual job directory
            job_dir = bilby_job.get_upload_directory()
            shutil.move(job_staging_dir, job_dir)

            # Generate the archive.tar.gz file
            p = subprocess.Popen(
                ["tar", "-cvf", "archive.tar.gz", "."],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=job_dir,
            )
            out, err = p.communicate()

            logger.info("Packing uploaded HDF5 job archive for %s had return code %s", job_name, p.returncode)
            logger.info("stdout: %s", out)
            logger.info("stderr: %s", err)

            if p.returncode != 0:
                msg = "Unable to repack the uploaded HDF5 job"
                raise RuntimeError(msg)

        # Job is validated and uploaded, return the job
        return bilby_job


def file_download_job_file(request, fdl):
    # Get the job path
    job_dir = fdl.job.get_upload_directory()

    # Make sure that there is no leading slash on the file path
    file_path = fdl.path.lstrip("/")

    # Get the full file path
    file_path = Path(job_dir) / file_path

    # Use a django file response object to stream the file back to the client
    return FileResponse(
        file_path.open("rb"),
        as_attachment="forceDownload" in request.GET,
        filename=file_path.name,
        content_type="application/octet-stream",
    )


def file_download_supporting_file(request, supporting_file):
    # Get the supporting file path
    job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(supporting_file.job.id)

    # Make sure that there is no leading slash on the file path
    file_path = job_dir / str(supporting_file.id)

    # Use a django file response object to stream the file back to the client
    return FileResponse(
        file_path.open("rb"),
        as_attachment="forceDownload" in request.GET,
        filename=supporting_file.file_name,
        content_type="application/octet-stream",
    )


def file_download_gwflow_file(request, gwflow_file):
    # 404 unless fully mirrored
    if not gwflow_file.uploaded:
        raise Http404

    # LIGO-only visibility
    if gwflow_file.job.ligo_only and not is_ligo_user(request.user):
        raise Http404

    file_path = Path(settings.GWFLOW_FILE_UPLOAD_DIR) / str(gwflow_file.job.id) / str(gwflow_file.id)
    if not file_path.exists():
        raise Http404

    return FileResponse(
        file_path.open("rb"),
        as_attachment="forceDownload" in request.GET,
        filename=gwflow_file.file_name,
        content_type="application/octet-stream",
    )


def file_download(request):
    # Get the file token from the request and make sure it's real
    token = request.GET.get("fileId", None)
    if not token:
        raise Http404

    try:
        # First try the token as a file download token
        fdl = FileDownloadToken.get_by_token(token)

        # Was a file found with this token?
        if fdl:
            return file_download_job_file(request, fdl)

        # Next try the token as a supporting file token
        supporting_file = SupportingFile.get_by_download_token(token)

        # Was a file found with this token?
        if supporting_file:
            return file_download_supporting_file(request, supporting_file)

        # Next try the token as a gwflow file token
        gwflow_file = GWFlowFile.get_by_download_token(token)

        # Was a file found with this token?
        if gwflow_file:
            return file_download_gwflow_file(request, gwflow_file)

        raise Http404
    except ValidationError as e:
        logger.warning("ValidationError in file_download for token: %s", token)
        raise Http404 from e


def create_event_id(_user, event_id, gps_time, trigger_id=None, nickname=None, is_ligo_event=False):
    EventID.create(
        event_id=event_id,
        trigger_id=trigger_id,
        nickname=nickname,
        is_ligo_event=is_ligo_event,
        gps_time=gps_time,
    )

    return f"EventID {event_id} succesfully created!"


def update_event_id(user, event_id, gps_time, trigger_id=None, nickname=None, is_ligo_event=None):
    event = EventID.get_by_event_id(event_id, user)
    event.update(
        trigger_id=trigger_id,
        nickname=nickname,
        is_ligo_event=is_ligo_event,
        gps_time=gps_time,
    )

    # Jobs need to be resynced to elastic search
    for job in event.bilbyjob_set.all():
        job.elastic_search_update()

    return f"EventID {event_id} succesfully updated!"


def delete_event_id(user, event_id):
    event = EventID.get_by_event_id(event_id, user)
    event.delete()
    return f"EventID {event_id} succesfully deleted!"


def upload_supporting_files(upload_tokens, uploaded_supporting_files):
    # Check that the job directory exists for this supporting file
    for upload_token, uploaded_supporting_file in zip(upload_tokens, uploaded_supporting_files, strict=True):
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(upload_token.job.id)
        job_dir.mkdir(parents=True, exist_ok=True)

        with (job_dir / str(upload_token.id)).open("wb") as supporting_file:
            # Write the uploaded file to the temporary file
            supporting_file.writelines(uploaded_supporting_file.chunks())
            supporting_file.flush()

        # Clear the token to indicate the file is uploaded
        upload_token.upload_token = None
        upload_token.save()

        # Check if there are any supporting uploads left for this job and submit the job if required
        if not SupportingFile.get_unuploaded_supporting_files(upload_token.job).exists():
            # All supporting files have been uploaded, now launch the job
            upload_token.job.submit()

    return True


def _health_view(request):
    return TemplateResponse(request, "bilbyui/base.html", {"page_title": "htmx-bootstrap"})


def _event_id_display_values(event_id):
    if event_id is None:
        return []

    return [value for value in (event_id.event_id, event_id.trigger_id, event_id.nickname) if value]


def _job_status_name(bilby_job, job_controller_jobs):
    if bilby_job.job_type == BilbyJobType.NORMAL:
        if bilby_job.id not in job_controller_jobs:
            return "Unknown"
        job_controller_job = job_controller_jobs[bilby_job.id]
        return JobStatus.display_name(job_controller_job["history"][0]["state"])
    elif bilby_job.job_type in (BilbyJobType.UPLOADED, BilbyJobType.EXTERNAL):
        return JobStatus.display_name(JobStatus.COMPLETED)
    else:
        return "Unknown"


def _build_public_job_rows(public_jobs_result):
    records = public_jobs_result["records"]
    page_size = public_jobs_result["page_size"]
    job_controller_jobs = public_jobs_result["job_controller_jobs"]
    jobs = public_jobs_result["jobs"]

    rows = []
    for record in records[:page_size]:
        bilby_job = jobs.get(int(record["_id"]))
        if bilby_job is None:
            continue

        job_source = record["_source"]

        status_name = _job_status_name(bilby_job, job_controller_jobs)

        rows.append(
            {
                "id": bilby_job.id,
                "user": job_source["user"]["name"],
                "name": job_source["job"]["name"],
                "description": job_source["job"]["description"] or "",
                "status_name": status_name,
                "status_badge_class": STATUS_BADGE_CLASSES.get(status_name, "primary"),
                "labels": list(bilby_job.labels.all()),
                "event_id_values": _event_id_display_values(bilby_job.event_id),
            }
        )

    return rows


def _build_user_job_rows(user_jobs_result, user):
    jobs = user_jobs_result["jobs"]
    page_size = user_jobs_result["page_size"]

    job_controller_ids = {job.job_controller_id: job.id for job in jobs if job.job_controller_id}
    job_controller_jobs = {}
    if job_controller_ids:
        job_controller_jobs = {
            job_controller_ids[job["id"]]: job for job in request_job_filter(user.id, ids=job_controller_ids.keys())[1]
        }

    rows = []
    for bilby_job in jobs[:page_size]:
        status_name = _job_status_name(bilby_job, job_controller_jobs)

        rows.append(
            {
                "id": bilby_job.id,
                "user": user.name,
                "name": bilby_job.name,
                "description": bilby_job.description or "",
                "status_name": status_name,
                "status_badge_class": STATUS_BADGE_CLASSES.get(status_name, "primary"),
                "labels": list(bilby_job.labels.all()),
                "event_id_values": _event_id_display_values(bilby_job.event_id),
            }
        )

    return rows


def public_jobs_view(request):
    page = max(int(request.GET.get("page", 1)), 1)
    search = request.GET.get("search", "")
    time_range = request.GET.get("time_range", "all")

    public_jobs_result = list_public_jobs(
        request.user,
        search=search,
        time_range=time_range,
        page=page,
    )

    context = {
        "rows": _build_public_job_rows(public_jobs_result),
        "search": search,
        "time_range": time_range,
        "page": page,
        "has_next": public_jobs_result["has_next"],
        "next_page": page + 1,
        "user": request.user,
        "jobs_list_url_name": "bilbyui:public_jobs",
    }

    if request.headers.get("HX-Request") == "true":
        return TemplateResponse(request, "bilbyui/_job_list_fragment.html", context)

    return TemplateResponse(request, "bilbyui/public_jobs.html", context)


@login_required
def my_jobs_view(request):
    page = max(int(request.GET.get("page", 1)), 1)
    search = request.GET.get("search", "")
    time_range = request.GET.get("time_range", "all")

    user_jobs_result = list_user_jobs(
        request.user,
        search=search,
        time_range=time_range,
        page=page,
    )

    context = {
        "rows": _build_user_job_rows(user_jobs_result, request.user),
        "search": search,
        "time_range": time_range,
        "page": page,
        "has_next": user_jobs_result["has_next"],
        "next_page": page + 1,
        "user": request.user,
        "jobs_list_url_name": "bilbyui:my_jobs",
    }

    if request.headers.get("HX-Request") == "true":
        return TemplateResponse(request, "bilbyui/_job_list_fragment.html", context)

    return TemplateResponse(request, "bilbyui/my_jobs.html", context)


def _get_view_job_or_404(job_id, user):
    try:
        job = get_job(job_id, user)
    except BilbyJob.DoesNotExist as e:
        raise Http404 from e
    except PermissionError as e:
        logger.warning("Permission error fetching job %s: %s", job_id, e, exc_info=True)
        raise Http404 from e

    if not BilbyJob.bilby_job_filter(BilbyJob.objects.filter(pk=job.id), user).exists():
        raise Http404

    return job


def _get_job_status_context(job, user):
    if job.job_type in (BilbyJobType.UPLOADED, BilbyJobType.EXTERNAL):
        status_name = JobStatus.display_name(JobStatus.COMPLETED)
        status_date = job.last_updated
    elif not job.job_controller_id:
        status_name = "Unknown"
        status_date = job.last_updated
    else:
        _, job_controller_jobs = request_job_filter(user.id, ids=[job.job_controller_id])
        if not job_controller_jobs:
            status_name = "Unknown"
            status_date = job.last_updated
        else:
            job_controller_job = job_controller_jobs[0]
            status_name = JobStatus.display_name(job_controller_job["history"][0]["state"])
            status_date = job_controller_job["history"][0]["timestamp"]

    return {
        "status_name": status_name,
        "status_badge_class": STATUS_BADGE_CLASSES.get(status_name, "primary"),
        "status_date": status_date,
    }


def _build_result_files(job):
    if job.job_type == BilbyJobType.EXTERNAL:
        external_job = ExternalBilbyJob.objects.get(job=job)
        return [
            {
                "path": external_job.url,
                "is_dir": False,
                "file_size": None,
                "download_token": None,
            }
        ]

    success, files = job.get_file_list()
    if not success:
        return []

    paths = [f["path"] for f in files if not f["isDir"]]
    tokens = FileDownloadToken.create(job, paths)
    token_dict = {token.path: token.token for token in tokens}

    return [
        {
            "path": file_entry["path"],
            "is_dir": file_entry["isDir"],
            "file_size": file_entry["fileSize"],
            "download_token": token_dict.get(file_entry["path"]),
        }
        for file_entry in files
    ]


def _available_labels_for_job(job):
    job_label_names = set(job.labels.values_list("name", flat=True))
    return Label.objects.filter(protected=False).exclude(name__in=job_label_names)


def _render_job_field_labels(request, job, error="", status=200, modifiable=None):
    if modifiable is None:
        modifiable = request.user.id == job.user_id
    return TemplateResponse(
        request,
        "bilbyui/_job_field_labels.html",
        {
            "job": job,
            "available_labels": _available_labels_for_job(job) if modifiable else [],
            "error": error,
            "modifiable": modifiable,
        },
        status=status,
    )


@login_required
@resolve_job_ref_view
def view_job_view(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)
    status = _get_job_status_context(job, request.user)
    modifiable = request.user.id == job.user_id

    return TemplateResponse(
        request,
        "bilbyui/view_job.html",
        {
            "job": job,
            "status_name": status["status_name"],
            "status_badge_class": status["status_badge_class"],
            "status_date": status["status_date"],
            "modifiable": modifiable,
            "available_labels": _available_labels_for_job(job) if modifiable else [],
        },
    )


@login_required
@resolve_job_ref_view
def view_job_parameters_partial(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    try:
        params = generate_parameter_output(job)
    except (AttributeError, KeyError, ValueError) as e:
        logger.exception(
            "Failed to generate parameter output for job %s: %s",
            job.id,
            type(e).__name__,
        )
        params = None

    return TemplateResponse(
        request,
        "bilbyui/_parameters.html",
        {"job": job, "params": params},
    )


@login_required
@resolve_job_ref_view
def view_job_results_partial(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    return TemplateResponse(
        request,
        "bilbyui/_results.html",
        {"job": job, "files": _build_result_files(job)},
    )


def _render_job_field_text(request, job, field, editing=False, error="", status=200, modifiable=None):
    if modifiable is None:
        modifiable = request.user.id == job.user_id
    value = job.name if field == "name" else job.description
    return TemplateResponse(
        request,
        "bilbyui/_job_field_text.html",
        {
            "field": field,
            "value": value,
            "job_id": job.id,
            "editing": editing,
            "error": error,
            "modifiable": modifiable,
        },
        status=status,
    )


@login_required
@resolve_job_ref_view
def view_job_field_partial(request, job_id, field):
    job = _get_view_job_or_404(job_id, request.user)

    if field not in ("name", "description"):
        raise Http404

    editing = request.GET.get("editing") == "1"
    if editing and request.user.id != job.user_id:
        raise Http404
    return _render_job_field_text(request, job, field, editing=editing)


@login_required
@resolve_job_ref_view
@require_POST
def edit_job_name(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    if request.user.id != job.user_id:
        raise Http404

    name = request.POST.get("name", "")

    try:
        validate_job_name(name)
    except ValueError as e:
        logger.warning("edit_job_name validation failed for job %s: %s", job_id, e)
        return _render_job_field_text(request, job, "name", editing=True, error=str(e), status=400)

    update_job(job_id, request.user, name=name)
    job.refresh_from_db()

    response = _render_job_field_text(request, job, "name", editing=False)
    response["HX-Trigger"] = "save-toast"
    return response


@login_required
@resolve_job_ref_view
@require_POST
def edit_job_description(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    if request.user.id != job.user_id:
        raise Http404

    description = request.POST.get("description", "")

    update_job(job_id, request.user, description=description)
    job.refresh_from_db()

    response = _render_job_field_text(request, job, "description", editing=False)
    response["HX-Trigger"] = "save-toast"
    return response


def _render_job_field_privacy(request, job, status=200):
    modifiable = request.user.id == job.user_id
    return TemplateResponse(
        request,
        "bilbyui/_job_field_privacy.html",
        {"job": job, "modifiable": modifiable},
        status=status,
    )


@login_required
@resolve_job_ref_view
@require_POST
def edit_job_privacy(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    if request.user.id != job.user_id:
        raise Http404

    # Checked checkbox means sharing (public); unchecked means private.
    private = "private" not in request.POST

    update_job(job_id, request.user, private=private)
    job.refresh_from_db()

    response = _render_job_field_privacy(request, job)
    response["HX-Trigger"] = "save-toast"
    return response


@login_required
@resolve_job_ref_view
@require_POST
def edit_job_labels(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    if request.user.id != job.user_id:
        raise Http404

    new_labels = set(request.POST.getlist("labels"))
    if "add" in request.POST:
        new_labels.add(request.POST["add"])
    if "remove" in request.POST:
        new_labels.discard(request.POST["remove"])

    protected_names = set(job.labels.filter(protected=True).values_list("name", flat=True))
    for name in protected_names:
        if name not in new_labels:
            return _render_job_field_labels(
                request,
                job,
                error="Protected labels cannot be removed.",
                status=400,
            )

    update_job(job_id, request.user, labels=list(new_labels))
    job.refresh_from_db()

    response = _render_job_field_labels(request, job)
    response["HX-Trigger"] = "save-toast"
    return response


def _render_job_field_event_id(request, job, error="", status=200, modifiable=None):
    if modifiable is None:
        modifiable = request.user.id == job.user_id
    return TemplateResponse(
        request,
        "bilbyui/_job_field_event_id.html",
        {
            "job": job,
            "all_event_ids": list_event_ids_for_user(request.user),
            "error": error,
            "modifiable": modifiable,
        },
        status=status,
    )


def _filter_event_ids_for_query(event_ids, query):
    q_lower = query.lower()
    return [
        event
        for event in event_ids
        if q_lower in (event.event_id or "").lower()
        or q_lower in (event.trigger_id or "").lower()
        or q_lower in (event.nickname or "").lower()
    ]


@login_required
def event_id_search(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return HttpResponse('<p class="text-muted">Type to search…</p>')

    job_id = request.GET.get("job_id")
    if not job_id:
        raise Http404

    job = _get_view_job_or_404(job_id, request.user)
    matches = _filter_event_ids_for_query(list_event_ids_for_user(request.user), query)

    if not matches:
        return HttpResponse('<p class="text-muted">No matches</p>')

    items = [
        render_to_string(
            "bilbyui/_event_id_result.html",
            {"event": event, "job": job},
            request=request,
        )
        for event in matches
    ]
    return HttpResponse(f'<ul class="list-group">{"".join(items)}</ul>')


@login_required
@resolve_job_ref_view
def event_id_modal(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)
    return TemplateResponse(request, "bilbyui/_event_id_modal.html", {"job": job})


@login_required
@resolve_job_ref_view
@require_POST
def edit_job_event_id(request, job_id):
    job = _get_view_job_or_404(job_id, request.user)

    if request.user.id != job.user_id:
        raise Http404

    event_id_str = request.POST.get("event_id", "")

    if event_id_str == "":
        job.event_id = None
    else:
        try:
            job.event_id = get_event_id(event_id_str, user=request.user)
        except EventID.DoesNotExist:
            return _render_job_field_event_id(
                request,
                job,
                error=f"Event ID '{event_id_str}' not found.",
                status=400,
            )
        except PermissionError as e:
            logger.warning("Unexpected exception editing event ID for job %s: %s", job.id, e)
            return _render_job_field_event_id(request, job, error=str(e), status=400)

    job.save()

    response = _render_job_field_event_id(request, job)
    response["HX-Trigger"] = "save-toast, close-modal"
    return response


@login_required
@resolve_job_ref_view
def file_download_redirect(request, job_id, token):
    job = _get_view_job_or_404(job_id, request.user)

    paths = FileDownloadToken.get_paths(job, [token])
    if None in paths:
        raise Http404

    if job.job_type == BilbyJobType.UPLOADED:
        return HttpResponseRedirect(f"/file_download/?fileId={token}")

    success, result = request_file_download_ids(job, paths, user_id=request.user.id)
    if not success:
        raise Http404

    return HttpResponseRedirect(f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/?fileId={result[0]}")


@login_required
@require_GET
def api_token_view(request):
    tokens = list_tokens(request.user)
    return TemplateResponse(request, "bilbyui/api_token.html", {"tokens": tokens})


@login_required
@require_POST
def api_token_create(request):
    name = request.POST.get("name", "").strip()
    if not name:
        return HttpResponse("Token name cannot be empty", status=400)
    max_name_length = APISessionToken._meta.get_field("name").max_length
    if len(name) > max_name_length:
        return HttpResponse(f"Token name must be at most {max_name_length} characters", status=400)

    try:
        token = create_token(request.user, name)
    except (ValidationError, IntegrityError):
        return HttpResponse(
            "Ensure you do not already have a token with the same name",
            status=400,
        )

    return TemplateResponse(
        request,
        "bilbyui/_token_create_success.html",
        {
            "name": name,
            "full_token": str(token.token),
            "token": serialize_token(token),
        },
    )


@login_required
@require_POST
def api_token_revoke(request, token_id):
    try:
        revoke_token(request.user, token_id)
    except (PermissionDenied, APISessionToken.DoesNotExist):
        raise Http404 from None

    response = HttpResponse(status=204)
    response["HX-Trigger"] = "token-revoked"
    return response


@require_GET
def not_found_view(request, **kwargs):
    return TemplateResponse(request, "bilbyui/not_found.html", status=404)


def _check_gwflow_ingest_user(user):
    ingest_user_id = getattr(settings, "GWFLOW_INGEST_USER", None)
    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or ingest_user_id is None
        or user.id != ingest_user_id
    ):
        raise GraphQLError("Permission Denied")


def _gwflow_pending_file(f):
    return GWFlowPendingFile(
        id=to_global_id("GWFlowFileNode", f.id),
        sname=f.job.sname,
        analysis_uid=f.analysis_uid,
        path=f.path,
        file_name=f.file_name,
        md5_sum=f.md5_sum,
    )


def upsert_gwflow_job(user, params):
    _check_gwflow_ingest_user(user)

    sname = params.sname

    with transaction.atomic():
        job, created = GWFlowJob.objects.get_or_create(sname=sname, defaults={"user": user})

        # ligo_only handling
        ligo_only_param = getattr(params, "ligo_only", None)
        if ligo_only_param is not None:
            job.ligo_only = ligo_only_param

        # Update current-state fields if provided
        schema_version_param = getattr(params, "schema_version", None)
        if schema_version_param is not None:
            job.schema_version = schema_version_param

        libraries_param = getattr(params, "libraries", None)
        if libraries_param is not None:
            job.libraries = libraries_param

        is_pruned_param = getattr(params, "is_pruned", None)
        if is_pruned_param is not None:
            job.is_pruned = is_pruned_param

        history_id_param = getattr(params, "current_history_id", None)
        if history_id_param is not None:
            job.current_history_id = history_id_param

        history_ts_param = getattr(params, "current_history_timestamp", None)
        if history_ts_param is not None:
            job.current_history_timestamp = history_ts_param

        # Best-effort event link
        event_id_param = getattr(params, "event_id", None)
        if event_id_param:
            try:
                event = EventID.objects.filter(Q(trigger_id=event_id_param) | Q(event_id=event_id_param)).first()
                if event:
                    job.event_id = event
            except Exception as e:
                logger.warning("EventID lookup failed for event_id %s on job %s: %s", event_id_param, sname, e)

        job.save()

        # Process file manifest
        file_entries = getattr(params, "files", None) or []
        for entry in file_entries:
            analysis_uid = getattr(entry, "analysis_uid", "") or ""
            path = entry.path
            file_name = entry.file_name
            file_size = getattr(entry, "file_size", None)
            md5_sum = getattr(entry, "md5_sum", "") or ""

            f_obj, f_created = GWFlowFile.objects.get_or_create(
                job=job,
                analysis_uid=analysis_uid,
                path=path,
                defaults={
                    "file_name": file_name,
                    "file_size": file_size,
                    "md5_sum": md5_sum,
                },
            )
            if not f_created:
                if md5_sum and f_obj.md5_sum != md5_sum:
                    f_obj.md5_sum = md5_sum
                    f_obj.file_name = file_name
                    f_obj.file_size = file_size
                    f_obj.uploaded = False
                    f_obj.save()
                else:
                    changed = False
                    if f_obj.file_name != file_name:
                        f_obj.file_name = file_name
                        changed = True
                    if file_size is not None and f_obj.file_size != file_size:
                        f_obj.file_size = file_size
                        changed = True
                    if changed:
                        f_obj.save()

    # ES update runs outside the transaction so a connection error does not
    # roll back the DB write.
    metadata_param = getattr(params, "metadata", None)
    if metadata_param:
        try:
            metadata_dict = json.loads(metadata_param)
        except Exception as e:
            raise GraphQLError("Invalid metadata JSON") from e
        gwflow_elastic_search_update(job, metadata_dict)

    pending_qs = job.files.filter(uploaded=False).select_related("job").order_by("job__sname", "analysis_uid", "path")
    files_pending = [_gwflow_pending_file(f) for f in pending_qs]

    return {
        "gwflow_job_id": to_global_id("GWFlowJobNode", job.id),
        "sname": job.sname,
        "created": created,
        "files_pending": files_pending,
    }


def upload_gwflow_file(user, gwflow_file_id, file):
    _check_gwflow_ingest_user(user)

    try:
        _, file_pk = from_global_id(gwflow_file_id)
        gwflow_file = GWFlowFile.objects.select_related("job").get(id=int(file_pk))
    except Exception as e:
        raise GraphQLError("Invalid gwflow_file_id") from e

    dest_dir = Path(settings.GWFLOW_FILE_UPLOAD_DIR) / str(gwflow_file.job.id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / str(gwflow_file.id)
    part_path = dest_dir / f"{gwflow_file.id}.part"

    hasher = hashlib.md5() if gwflow_file.md5_sum else None
    bytes_written = 0

    try:
        with part_path.open("wb") as f_out:
            for chunk in file.chunks():
                f_out.write(chunk)
                bytes_written += len(chunk)
                if hasher:
                    hasher.update(chunk)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise

    if gwflow_file.md5_sum and hasher:
        calculated_md5 = hasher.hexdigest()
        if calculated_md5 != gwflow_file.md5_sum:
            if part_path.exists():
                part_path.unlink()
            if dest_path.exists():
                dest_path.unlink()
            raise GraphQLError("MD5 checksum mismatch")

    part_path.replace(dest_path)

    gwflow_file.uploaded = True
    gwflow_file.file_size = bytes_written
    gwflow_file.save(update_fields=["uploaded", "file_size"])

    return {"success": True, "file_size": bytes_written}


def link_bilby_job_to_gwflow(user, job_id, sname, analysis_uid):
    _check_gwflow_ingest_user(user)

    try:
        _, job_pk = from_global_id(job_id)
        job = BilbyJob.get_by_id(int(job_pk), user)
    except Exception as e:
        raise GraphQLError("Invalid job_id") from e

    if not sname:
        old_parent = job.gwflow_job
        job.gwflow_job = None
        job.gwflow_analysis_uid = ""
        job.save()
        if old_parent:
            update_gwflow_child_job_ids(old_parent)
        return {"success": True}

    try:
        gwflow_job = GWFlowJob.objects.get(sname=sname)
    except GWFlowJob.DoesNotExist as e:
        raise GraphQLError(f"GWFlowJob with sname '{sname}' does not exist") from e

    duplicate_qs = gwflow_job.bilby_jobs.filter(gwflow_analysis_uid=analysis_uid).exclude(id=job.id)
    if duplicate_qs.exists():
        raise GraphQLError(f"analysis_uid '{analysis_uid}' already linked to another BilbyJob on GWFlowJob '{sname}'")

    job.gwflow_job = gwflow_job
    job.gwflow_analysis_uid = analysis_uid
    job.save()

    update_gwflow_child_job_ids(gwflow_job)

    return {"success": True}


def get_gwflow_pending_files(user):
    _check_gwflow_ingest_user(user)

    pending_files = (
        GWFlowFile.objects.filter(uploaded=False).select_related("job").order_by("job__sname", "analysis_uid", "path")
    )

    return [_gwflow_pending_file(f) for f in pending_files]
