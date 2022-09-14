import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import bilby_pipe
from bilby_pipe.data_generation import DataGenerationInput
from bilby_pipe.parser import create_parser
from bilby_pipe.utils import convert_string_to_dict
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.http import Http404, FileResponse

from .models import BilbyJob, Label, EventID, FileDownloadToken, SupportingFile
from .utils.ini_utils import bilby_args_to_ini_string, bilby_ini_string_to_args


def validate_job_name(name):
    if len(name) < 5:
        raise Exception('Job name must be at least 5 characters long.')

    if len(name) > 30:
        raise Exception('Job name must be less than 30 characters long.')

    pattern = re.compile(r"^[0-9a-z_-]+\Z", flags=re.IGNORECASE | re.ASCII)
    if not pattern.match(name):
        raise Exception('Job name must not contain any spaces or special characters.')


def create_bilby_job(user, params):
    validate_job_name(params.details.name)

    # Check the ligo permissions and ligo job status
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

    event_id = EventID.get_by_event_id(params.data.event_id, user) if params.data.event_id else None

    bilby_job = BilbyJob.objects.create(
        user_id=user.user_id,
        name=params.details.name,
        description=params.details.description,
        private=params.details.private,
        is_ligo_job=is_ligo_job,
        ini_string=ini_string,
        cluster=params.details.cluster,
        event_id=event_id
    )

    # Submit the job to the job controller
    bilby_job.submit()

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
        SupportingFile.PSD: 'psd_dict',
        SupportingFile.CALIBRATION: 'spline_calibration_envelope_dict',
        SupportingFile.NUMERICAL_RELATIVITY: 'numerical_relativity_file',
        SupportingFile.DISTANCE_MARGINALIZATION_LOOKUP_TABLE: 'distance_marginalization_lookup_table',
        SupportingFile.DATA: 'data_dict'
    }.items():
        if config_name == 'psd_dict':
            if not psd_dict:
                continue

            config = convert_string_to_dict(psd_dict, "psd-dict")
        elif config_name == 'distance_marginalization_lookup_table':
            # Bilby pipe has a weird way to deal with default distance marginalisation tables. If the distance
            # marginalisation lookup table is None, then bilby_pipe will copy a default one for the specified prior
            # in to the current working directory. Then upon our code trying to check if that file exists, we get an
            # error. Instead, we need to check if the provided marginalisation lookup table is one of the defaults, and
            # ignore it if it is. See get_distance_file_lookup_table() in
            # https://git.ligo.org/lscsoft/bilby_pipe/-/blob/master/bilby_pipe/input.py#L781

            config = getattr(parser, config_name)
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
            # Check if this configuration parameter is set in the parser
            if not hasattr(parser, config_name):
                continue

            config = getattr(parser, config_name)
            if config is None:
                continue

        if type(config) is dict:
            # Handle this configuration item as a dictionary of files
            # ie. {'L1': './supporting_files/psd/L1-psd.dat', 'V1': './supporting_files/psd/V1-psd.dat'}
            supporting_files.setdefault(supporting_file_type, [])
            for k, f in config.items():
                supporting_files[supporting_file_type].append({k: f})

            # Clear this configuration item from the parser
            setattr(parser, config_name, None)
            setattr(args, config_name, None)

        elif type(config) is str:
            # This config item is a single file
            supporting_files.setdefault(supporting_file_type, config)

            # Clear this configuration item from the parser
            setattr(parser, config_name, None)
            setattr(args, config_name, None)

        else:
            logging.error(f"Got unknown supporting file type for {config_name}: {str(config)}")

    return supporting_files


def create_bilby_job_from_ini_string(user, params):
    # Parse the job ini file and create a bilby input class that can be used to read values from the ini
    args = bilby_ini_string_to_args(params.ini_string.ini_string.encode('utf-8'))
    args.idx = None
    args.ini = None

    if args.outdir == '.':
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
        parser,
        args,
        prior_file,
        gps_file,
        timeslide_file,
        injection_file,
        psd_dict
    )

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
    validate_job_name(params.details.name)
    args.label = params.details.name

    # Convert the modified arguments back to an ini string
    ini_string = bilby_args_to_ini_string(args)

    bilby_job = BilbyJob(
        user_id=user.user_id,
        name=params.details.name,
        description=params.details.description,
        private=params.details.private,
        ini_string=ini_string,
        is_ligo_job=is_ligo_job,
        cluster=params.details.cluster
    )
    bilby_job.save()

    # Save any supporting file records
    supporting_file_details = SupportingFile.save_from_parsed(bilby_job, supporting_files)

    # Submit the job to the job controller if there are no supporting files
    if not bilby_job.has_supporting_files():
        bilby_job.submit()

    return bilby_job, supporting_file_details


def update_bilby_job(job_id, user, private=None, labels=None, event_id=None, name=None, description=None):
    bilby_job = BilbyJob.get_by_id(job_id, user)

    if user.user_id == bilby_job.user_id:
        if labels is not None:
            # Preserve protected labels
            protected_labels = bilby_job.labels.filter(protected=True)
            bilby_job.labels.set(Label.filter_by_name(labels) | protected_labels)

        if event_id is not None:
            bilby_job.event_id = None if event_id == '' else EventID.objects.get(event_id=event_id)

        if private is not None:
            bilby_job.private = private

        if name is not None:
            validate_job_name(name)
            bilby_job.name = name

        if description is not None:
            bilby_job.description = description

        bilby_job.save()

        return 'Job saved!'

    elif user.user_id in settings.PERMITTED_EVENT_CREATION_USER_IDS and event_id is not None:
        bilby_job.event_id = None if event_id == '' else EventID.objects.get(event_id=event_id)

        bilby_job.save()

        return 'Job saved'

    else:
        raise Exception('You must own the job to change it!')


def upload_bilby_job(upload_token, details, job_file):
    # Check that the uploaded file is a tar.gz file
    if not job_file.name.endswith('tar.gz'):
        raise Exception("Job upload should be a tar.gz file")

    # Check that the job upload directory exists
    os.makedirs(settings.JOB_UPLOAD_STAGING_DIR, exist_ok=True)

    # Write out the uploaded job to disk and unpack the archive to a temporary staging directory
    with TemporaryDirectory(dir=settings.JOB_UPLOAD_STAGING_DIR) as job_staging_dir, \
            NamedTemporaryFile(dir=settings.JOB_UPLOAD_STAGING_DIR, suffix='.tar.gz') as job_upload_file, \
            UploadedFile(job_file) as django_job_file:

        # Write the uploaded file to the temporary file
        for c in django_job_file.chunks():
            job_upload_file.write(c)
        job_upload_file.flush()

        # Unpack the archive to the temporary directory
        p = subprocess.Popen(
            ['tar', '-xvf', job_upload_file.name, '.'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=job_staging_dir
        )
        out, err = p.communicate()

        logging.info(f"Unpacking uploaded job archive {job_file.name} had return code {p.returncode}")
        logging.info(f"stdout: {out}")
        logging.info(f"stderr: {err}")

        if p.returncode != 0:
            raise Exception("Invalid or corrupt tar.gz file")

        # Validate the directory structure, this should include 'data', 'result', and 'results_page' at minimum
        for directory in [
            'data',
            'result',
            'results_page'
        ]:
            if not os.path.isdir(os.path.join(job_staging_dir, directory)):
                raise Exception(f"Invalid directory structure, expected directory ./{directory} to exist.")

        # Find the config complete ini
        ini_file = list(filter(
            lambda x: os.path.isfile(os.path.join(job_staging_dir, x)) and x.endswith("_config_complete.ini"),
            os.listdir(job_staging_dir)
        ))

        if len(ini_file) != 1:
            raise Exception(
                "Invalid number of ini files ending in `_config_complete.ini`. There should be exactly one."
            )

        ini_file = ini_file[0]

        # Read the ini file
        with open(os.path.join(job_staging_dir, ini_file), 'r') as f:
            ini_content = f.read()

        # Parse the ini file to check it's validity
        args = bilby_ini_string_to_args(ini_content.encode('utf-8'))
        validate_job_name(args.label)

        args.idx = None
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
            parser,
            args,
            prior_file,
            gps_file,
            timeslide_file,
            injection_file,
            psd_dict
        )

        # Verify that a non-ligo user can't upload a ligo job, and check if this job is a ligo job or not
        if args.n_simulation == 0 and (any([channel != 'GWOSC' for channel in (parser.channel_dict or {}).values()])):
            # This is a real job, with a channel that is not GWOSC
            if not upload_token.is_ligo:
                # User is not a ligo user, so they may not submit this job
                raise Exception("Non-LIGO members may only upload real jobs on GWOSC channels")
            else:
                is_ligo_job = True
        else:
            is_ligo_job = False

        # Convert the modified arguments back to an ini string
        ini_string = bilby_args_to_ini_string(args)

        with transaction.atomic():
            # This is in an atomic block in case:-
            # * The ini file somehow ends up broken
            # * The final move of the staging directory to the job directory raises an exception (Disk full etc)
            # * The generation of the archive.tar.gz file fails (Disk full etc)

            # Create the bilby job
            bilby_job = BilbyJob(
                user_id=upload_token.user_id,
                name=args.label,
                description=details.description,
                private=details.private,
                ini_string=ini_string,
                is_ligo_job=is_ligo_job,
                is_uploaded_job=True
            )
            bilby_job.save()

            # Save any supporting file records
            supporting_file_details = SupportingFile.save_from_parsed(bilby_job, supporting_files, uploaded=True)

            # Check that the job directory exists for this supporting file
            supporting_file_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(bilby_job.id)
            supporting_file_dir.mkdir(exist_ok=True, parents=True)

            # Make sure the source supporting file exists
            for supporting_file in supporting_file_details:
                source_file = Path(job_staging_dir) / supporting_file['file_path']
                if not source_file.is_file():
                    raise Exception(f"Supporting file {supporting_file['file_path']} does not exist.")

                # Because we're in a transaction here, the bulk_create in `SupportingFile.save_from_parsed` isn't saved
                # so we need to fetch it again from the database to get the inserted ID
                supporting_file_instance = SupportingFile.objects.get(download_token=supporting_file['download_token'])
                source_file = Path(job_staging_dir) / supporting_file['file_path']
                shutil.copyfile(source_file, supporting_file_dir / str(supporting_file_instance.id))

            # Now we have the bilby job id, we can move the staging directory to the actual job directory
            job_dir = bilby_job.get_upload_directory()
            shutil.move(job_staging_dir, job_dir)

            # Finally generate the archive.tar.gz file
            p = subprocess.Popen(
                ['tar', '-cvf', 'archive.tar.gz', '.'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=job_dir
            )
            out, err = p.communicate()

            logging.info(f"Packing uploaded job archive for {job_file.name} had return code {p.returncode}")
            logging.info(f"stdout: {out}")
            logging.info(f"stderr: {err}")

            if p.returncode != 0:
                raise Exception("Unable to repack the uploaded job")

        # Job is validated and uploaded, return the job
        return bilby_job


def file_download_job_file(request, fdl):
    # Get the job path
    job_dir = fdl.job.get_upload_directory()

    # Make sure that there is no leading slash on the file path
    file_path = fdl.path
    while len(file_path) and file_path[0] == '/':
        file_path = file_path[1:]

    # Get the full file path
    file_path = os.path.join(job_dir, file_path)

    # Use a django file response object to stream the file back to the client
    return FileResponse(
        open(file_path, 'rb'),
        as_attachment='forceDownload' in request.GET,
        filename=os.path.basename(file_path),
        content_type='application/octet-stream'
    )


def file_download_supporting_file(request, supporting_file):
    # Get the supporting file path
    job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(supporting_file.job.id)

    # Make sure that there is no leading slash on the file path
    file_path = job_dir / str(supporting_file.id)

    # Use a django file response object to stream the file back to the client
    return FileResponse(
        open(file_path, 'rb'),
        as_attachment='forceDownload' in request.GET,
        filename=supporting_file.file_name,
        content_type='application/octet-stream'
    )


def file_download(request):
    # Get the file token from the request and make sure it's real
    token = request.GET.get('fileId', None)
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

        raise Http404
    except ValidationError:
        raise Http404


def create_event_id(user, event_id, gps_time, trigger_id=None, nickname=None, is_ligo_event=False):
    EventID.create(
        event_id=event_id,
        trigger_id=trigger_id,
        nickname=nickname,
        is_ligo_event=is_ligo_event,
        gps_time=gps_time,
    )

    return f'EventID {event_id} succesfully created!'


def update_event_id(user, event_id, gps_time, trigger_id=None, nickname=None, is_ligo_event=None):
    event = EventID.get_by_event_id(event_id, user)
    event.update(
        trigger_id=trigger_id,
        nickname=nickname,
        is_ligo_event=is_ligo_event,
        gps_time=gps_time,
    )

    return f'EventID {event_id} succesfully updated!'


def delete_event_id(user, event_id):
    event = EventID.get_by_event_id(event_id, user)
    event.delete()
    return f'EventID {event_id} succesfully deleted!'


def upload_supporting_files(upload_tokens, uploaded_supporting_files):
    # Check that the job directory exists for this supporting file
    for upload_token, uploaded_supporting_file in zip(upload_tokens, uploaded_supporting_files):
        job_dir = Path(settings.SUPPORTING_FILE_UPLOAD_DIR) / str(upload_token.job.id)
        os.makedirs(job_dir, exist_ok=True)

        with open(job_dir / str(upload_token.id), 'wb') as supporting_file:
            # Write the uploaded file to the temporary file
            for c in uploaded_supporting_file.chunks():
                supporting_file.write(c)
            supporting_file.flush()

        # Clear the token to indicate the file is uploaded
        upload_token.upload_token = None
        upload_token.save()

        # Check if there are any supporting uploads left for this job and submit the job if required
        if not SupportingFile.get_unuploaded_supporting_files(upload_token.job).exists():
            # All supporting files have been uploaded, now launch the job
            upload_token.job.submit()

    return True
