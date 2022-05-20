import decimal
from decimal import Decimal
from math import floor

from bilby_pipe.data_generation import DataGenerationInput
from bilby_pipe.input import Input
from bilby_pipe.utils import logger

from bilbyui.types import JobParameterOutput, JobDetailsOutput, ChannelsOutput, DataOutput, DetectorOutput, \
    PriorOutput, SamplerOutput, WaveformOutput
from bilbyui.utils.ini_utils import bilby_ini_string_to_args

# Override the log level so it's silent
logger.setLevel('CRITICAL')


def to_dec(val):
    if type(val) is Decimal:
        return val

    # Nothing to do if the value is None
    if val is None:
        return None

    try:
        # If the value is a string, just return it as a Decimal
        if type(val) is str:
            return Decimal(val)
    except decimal.InvalidOperation:
        # If the string is not able to be converted, simply assume it's a string type not representing a decimal
        # and return the original value
        return val

    # It's a numeric type, if there is a remainder, convert the value to a string and parse it with Decimal
    if val - floor(val):
        return Decimal(str(val))
    else:
        # The number is whole, cast it to an int and then parse it with Decimal
        return Decimal(int(val))


def generate_parameter_output(job):
    """
    Generates a complete JobParameterOutput for a job

    :input job: The BilbyJob instance to generate the JobParameterOutput for
    :result: The complete JobParameterOutput
    """

    # Parse the job ini file and create a bilby input class that can be used to read values from the ini
    args = bilby_ini_string_to_args(job.ini_string.encode('utf-8'))
    args.idx = None
    args.ini = None

    # Sanitize the output directory
    if args.outdir == '.':
        args.outdir = "./"

    # Sanitize supporting files for the DataGenerationInput step. None of the supporting files are required for the
    # parameter generation when querying a job.
    sanitized_fields = [
        'psd_dict',
        'spline_calibration_envelope_dict',
        'gps_file',
        'timeslide_file',
        'injection_file',
        'numerical_relativity_file',
        'distance_marginalization_lookup_table',
        'data_dict'
    ]

    # Prior files can be defaults (like 4s, 32s etc), if it's one of the defaults - then the prior file is valid, so
    # leave the prior file as is.
    if args.prior_file not in Input([], []).get_default_prior_files():
        sanitized_fields.append('prior_file')

    for field in sanitized_fields:
        if hasattr(args, field):
            setattr(args, field, None)

    parser = DataGenerationInput(args, [], create_data=False)

    # Channels
    channels = ChannelsOutput()
    if parser.channel_dict:
        for attr, key in (
                ('hanford_channel', 'H1'),
                ('livingston_channel', 'L1'),
                ('virgo_channel', 'V1'),
        ):
            setattr(channels, attr, parser.channel_dict.get(key, None))

    # Data
    data = DataOutput(
        data_choice="simulated" if args.n_simulation else "real",
        # trigger_time = None or str representing the decimal value
        trigger_time=to_dec(args.trigger_time),
        channels=channels
    )

    # Detector
    # Trigger the duration setter
    parser.duration = args.duration
    detector = DetectorOutput(
        duration=to_dec(parser.duration),
        sampling_frequency=to_dec(parser.sampling_frequency),
    )
    for k, v in {
        ('hanford', 'H1'),
        ('livingston', 'L1'),
        ('virgo', 'V1')
    }:
        if v in parser.detectors:
            setattr(detector, k, True)
            setattr(detector, f"{k}_minimum_frequency", to_dec(parser.minimum_frequency_dict[v]))
            setattr(detector, f"{k}_maximum_frequency", to_dec(parser.maximum_frequency_dict[v]))
        else:
            setattr(detector, k, False)
            setattr(detector, f"{k}_minimum_frequency", to_dec(parser.minimum_frequency))
            setattr(detector, f"{k}_maximum_frequency", to_dec(parser.maximum_frequency))

    # Prior
    prior = PriorOutput(
        # args.prior_file is correct here rather than parser. parser actually fills out the entire path to the prior
        # file
        prior_default=args.prior_file
    )

    # Sampler
    # Trigger sampler setter in the parser
    parser.sampler = args.sampler
    parser.request_cpus = args.request_cpus
    parser.sampler_kwargs = args.sampler_kwargs
    sampler = SamplerOutput(
        sampler_choice=parser.sampler,
        cpus=args.request_cpus
    )

    for k, v in parser.sampler_kwargs.items():
        setattr(sampler, k, to_dec(v))

    # Waveform
    model = "unknown"
    if parser.frequency_domain_source_model == "lal_binary_black_hole":
        model = "binaryBlackHole"
    elif parser.frequency_domain_source_model == "lal_binary_neutron_star":
        model = "binaryNeutronStar"

    waveform = WaveformOutput(
        model=model
    )

    return JobParameterOutput(
        details=JobDetailsOutput(
            name=job.name,
            description=job.description,
            private=job.private
        ),
        data=data,
        detector=detector,
        prior=prior,
        sampler=sampler,
        waveform=waveform
    )
