import json
import functools
import logging
from collections import OrderedDict

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


def compare_ini_kvs(test, job, ini):
    args = parse_test_ini(ini)
    for k, v in args.items():
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


def create_test_ini_string(config_dict={}, complete=False):
    if complete or (config_dict == {}):
        config_dict = complete_config_dict(config_dict)

    return construct_ini_string_from_dict(config_dict)


def silence_errors(func):
    @functools.wraps(func)
    def wrapper_silence_errors(*args, **kwargs):
        try:
            logging.disable(logging.ERROR)
            func(*args, **kwargs)
        finally:
            logging.disable(logging.NOTSET)
    return wrapper_silence_errors
