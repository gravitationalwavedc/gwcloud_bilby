from decimal import Decimal
from math import floor

from bilby_pipe.data_generation import DataGenerationInput
from bilby_pipe.utils import logger

from bilbyui.types import JobParameterOutput, JobDetailsOutput, ChannelsOutput, DataOutput, DetectorOutput, \
    PriorOutput, SamplerOutput, WaveformOutput
from bilbyui.utils.parse_ini_file import bilby_ini_to_args

# Override the log level so it's silent
logger.setLevel('CRITICAL')


def to_dec(val):
    if type(val) is Decimal:
        return val

    # Nothing to do if the value is None
    if val is None:
        return None

    # If the value is a string, just return it as a Decimal
    if type(val) is str:
        return Decimal(val)

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
    args = bilby_ini_to_args(job.ini_string.encode('utf-8'))
    args.idx = None
    args.ini = None

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
