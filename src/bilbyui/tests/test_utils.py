import functools
import json
import logging
import os
import tarfile
from collections import OrderedDict
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile

from bilbyui.models import IniKeyValue
from bilbyui.utils.ini_utils import bilby_ini_string_to_args


def parse_test_ini(ini):
    # Get the args from the ini
    args = bilby_ini_string_to_args(ini.encode('utf-8'))

    # Iterate over the parsed ini configuration and generate a result dict
    result = {}
    for idx, key in enumerate(vars(args)):
        result[key] = dict(value=getattr(args, key), index=idx)

    return result


def compare_ini_kvs(test, job, ini, ignored=None):
    if ignored is None:
        ignored = []

    args = parse_test_ini(ini)
    for k, v in args.items():
        if k in ignored:
            continue

        test.assertTrue(
            IniKeyValue.objects.filter(
                job=job,
                key=k,
                value__in=[
                    json.dumps([v['value']]),
                    json.dumps(v['value']),
                    json.dumps(float(v['value']) if type(v['value']) is int else v['value'])
                ],
                index=v['index']
            ).exists(),
            f"ini k/v didn't exist when it should: {k}, {json.dumps(v['value'])} ({v['index']})"
        )


def complete_config_dict(config_dict):
    complete_dict = OrderedDict([
        ################################################################################
        # Calibration arguments
        ################################################################################

        ("calibration-model", None),
        ("spline-calibration-envelope-dict", None),
        ("spline-calibration-nodes", 5),
        ("spline-calibration-amplitude-uncertainty-dict", None),
        ("spline-calibration-phase-uncertainty-dict", None),

        ################################################################################
        # Data generation arguments
        ################################################################################

        ("ignore-gwpy-data-quality-check", True),
        ("gps-tuple", None),
        ("gps-file", None),
        ("timeslide-file", None),
        ("trigger-time", 1128678900.4),
        ("gaussian-noise", True),
        ("n-simulation", 1),
        ("data-dict", None),
        ("data-format", None),
        ("channel-dict", {'H1': 'GWOSC', 'L1': 'GWOSC'}),

        ################################################################################
        # Detector arguments
        ################################################################################

        ("coherence-test", False),
        ("detectors", ['H1', 'L1']),
        ("duration", 4),
        ("generation-seed", None),
        ("psd-dict", None),
        ("psd-fractional-overlap", 0.5),
        ("post-trigger-duration", 2.0),
        ("sampling-frequency", 16384),
        ("psd-length", 32),
        ("psd-maximum-duration", 1024),
        ("psd-method", "median"),
        ("psd-start-time", None),
        ("maximum-frequency", {'H1': '1024', 'L1': '1024'}),
        ("minimum-frequency", {'H1': '20', 'L1': '20'}),
        ("zero-noise", False),
        ("tukey-roll-off", 0.4),

        ################################################################################
        # Injection arguments
        ################################################################################

        ("injection", False),
        ("injection-dict", None),
        ("injection-file", None),
        ("injection-numbers", None),
        ("injection-waveform-approximant", None),

        ################################################################################
        # Job submission arguments
        ################################################################################

        ("accounting", None),
        ("label", "TestJob"),
        ("local", False),
        ("local-generation", False),
        ("local-plot", False),
        ("outdir", "."),
        ("periodic-restart-time", 2147483647),
        ("request-memory", 4.0),
        ("request-memory-generation", None),
        ("request-cpus", 1),
        ("singularity-image", None),
        ("scheduler", "slurm"),
        ("scheduler-args", None),
        ("scheduler-module", None),
        ("scheduler-env", "/venv/bin/activate"),
        ("submit", False),
        ("transfer-files", True),
        ("log-directory", None),
        ("online-pe", False),
        ("osg", False),

        ################################################################################
        # Likelihood arguments
        ################################################################################

        ("distance-marginalization", False),
        ("distance-marginalization-lookup-table", None),
        ("phase-marginalization", False),
        ("time-marginalization", False),
        ("jitter-time", True),
        ("likelihood-type", "GravitationalWaveTransient"),
        ("roq-folder", None),
        ("roq-scale-factor", 1),
        ("extra-likelihood-kwargs", None),

        ################################################################################
        # Output arguments
        ################################################################################

        ("create-plots", True),
        ("plot-calibration", False),
        ("plot-corner", True),
        ("plot-marginal", True),
        ("plot-skymap", True),
        ("plot-waveform", True),
        ("plot-format", "png"),
        ("create-summary", False),
        ("email", None),
        ("existing-dir", None),
        ("webdir", None),
        ("summarypages-arguments", None),

        ################################################################################
        # Prior arguments
        ################################################################################

        ("default-prior", "BBHPriorDict"),
        ("deltaT", 0.2),
        ("prior-file", "4s"),
        ("prior-dict", None),
        ("convert-to-flat-in-component-mass", False),

        ################################################################################
        # Post processing arguments
        ################################################################################

        ("postprocessing-executable", None),
        ("postprocessing-arguments", None),

        ################################################################################
        # Sampler arguments
        ################################################################################

        ("sampler", "dynesty"),
        ("sampling-seed", None),
        ("n-parallel", 1),
        ("sampler-kwargs", "Default"),

        ################################################################################
        # Waveform arguments
        ################################################################################

        ("waveform-generator", "bilby.gw.waveform_generator.WaveformGenerator"),
        ("reference-frequency", 20),
        ("waveform-approximant", "IMRPhenomPv2"),
        ("catch-waveform-errors", True),
        ("pn-spin-order", -1),
        ("pn-tidal-order", -1),
        ("pn-phase-order", -1),
        ("pn-amplitude-order", 0),
        ("frequency-domain-source-model", "lal_binary_black_hole")
    ])

    complete_dict.update(config_dict)

    return complete_dict


def construct_ini_string_from_dict(config_dict):
    config_line_list = [
        f"{key}={value}" for key, value in config_dict.items()
    ]

    return '\n'.join(config_line_list)


def create_test_ini_string(config_dict=None, complete=False):
    if config_dict is None:
        config_dict = {}

    if complete or (config_dict == {}):
        config_dict = complete_config_dict(config_dict)

    return construct_ini_string_from_dict(config_dict)


def silence_errors(func):
    @functools.wraps(func)
    def wrapper_silence_errors(*args, **kwargs):
        try:
            logging.disable(logging.ERROR)
            return func(*args, **kwargs)
        finally:
            logging.disable(logging.NOTSET)

    return wrapper_silence_errors


def create_test_upload_data(ini_content, job_label, include_result=True, include_results_page=True,
                            include_data=True, multiple_ini_files=False, no_ini_file=False,
                            supporting_files=None):
    if supporting_files is None:
        supporting_files = []

    # Create a temporary directory to add job data to
    with TemporaryDirectory() as d:
        if ini_content and not no_ini_file:
            with open(os.path.join(d, f'{job_label}_config_complete.ini'), 'w') as ini:
                ini.write(ini_content)

            with open(os.path.join(d, 'unrelated.ini'), 'w') as ini:
                ini.write(ini_content)

            if multiple_ini_files:
                with open(os.path.join(d, f'{job_label}2_config_complete.ini'), 'w') as ini:
                    ini.write(ini_content)

                with open(os.path.join(d, f'{job_label}3_config_complete.ini'), 'w') as ini:
                    ini.write(ini_content)

        if include_result:
            os.makedirs(os.path.join(d, 'result'))
            open(os.path.join(d, 'result', f'{job_label}_intrinsic_corner.png'), 'a').close()
            open(os.path.join(d, 'result', f'{job_label}_extrinsic_corner.png'), 'a').close()
            open(os.path.join(d, 'result', f'{job_label}_test.png'), 'a').close()

        if include_results_page:
            os.makedirs(os.path.join(d, 'results_page'))
            open(os.path.join(d, 'results_page', 'overview.html'), 'a').close()

        if include_data:
            os.makedirs(os.path.join(d, 'data'))
            open(os.path.join(d, 'data', f'H1_{job_label}_generation_frequency_domain_data.png'), 'a').close()
            open(os.path.join(d, 'data', f'L1_{job_label}_generation_frequency_domain_data.png'), 'a').close()

        for archive_path in supporting_files:
            file_path = Path(d) / Path(archive_path)
            file_path.parent.mkdir(exist_ok=True, parents=True)
            file_path.touch()

        # Create a temporary tar.gz file to write the directory contents to
        with NamedTemporaryFile(suffix='.tar.gz') as tgz:
            with tarfile.open(tgz.name, "w:gz") as tar_handle:
                # Change the working directory to the temporary directory so we don't have full paths in the tar.gz
                wd = os.getcwd()
                os.chdir(d)

                # Walk the temporary directory and write the files to the archive
                for root, dirs, files in os.walk('.'):
                    for file in files:
                        tar_handle.add(os.path.join(root, file))

            # Return to the original working directory
            os.chdir(wd)

            # Return the contents of the tarfile
            return tgz.read()


def get_file_download_tokens(response):
    # Returns all downloadTokens for a bilbyResultFiles response where the file is not a directory

    download_tokens = [
        f['downloadToken']
        for f in filter(lambda x: not x['isDir'], response.data['bilbyResultFiles']['files'])
    ]
    return download_tokens


def get_files(response):
    # Returns all files for a bilbyResultFiles response where the file is not a directory

    files = [
        f
        for f in filter(lambda x: not x['isDir'], response.data['bilbyResultFiles']['files'])
    ]
    return files
