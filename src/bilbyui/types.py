import graphene
from graphene_file_upload.scalars import Upload


class JobStatusType(graphene.ObjectType):
    name = graphene.String()
    number = graphene.Int()
    date = graphene.String()


class BilbyJobSupportingFile(graphene.ObjectType):
    file_path = graphene.String()
    token = graphene.String()


class BilbyJobCreationResult(graphene.ObjectType):
    job_id = graphene.String()
    supporting_files = graphene.List(BilbyJobSupportingFile)


class CalibrationCommon:
    pass


class ChannelsCommon:
    hanford_channel = graphene.String()
    livingston_channel = graphene.String()
    virgo_channel = graphene.String()


class ChannelsInput(graphene.InputObjectType, ChannelsCommon):
    pass


class ChannelsOutput(graphene.ObjectType, ChannelsCommon):
    pass


class DataCommon:
    data_choice = graphene.String()
    trigger_time = graphene.Decimal()


class DataInput(graphene.InputObjectType, DataCommon):
    channels = ChannelsInput()
    event_id = graphene.String()


class DataOutput(graphene.ObjectType, DataCommon):
    channels = graphene.Field(ChannelsOutput)


class DetectorCommon:
    hanford = graphene.Boolean()
    hanford_minimum_frequency = graphene.Decimal()
    hanford_maximum_frequency = graphene.Decimal()

    livingston = graphene.Boolean()
    livingston_minimum_frequency = graphene.Decimal()
    livingston_maximum_frequency = graphene.Decimal()

    virgo = graphene.Boolean()
    virgo_minimum_frequency = graphene.Decimal()
    virgo_maximum_frequency = graphene.Decimal()

    duration = graphene.Decimal()
    sampling_frequency = graphene.Decimal()


class DetectorInput(graphene.InputObjectType, DetectorCommon):
    pass


class DetectorOutput(graphene.ObjectType, DetectorCommon):
    pass


class InjectionCommon:
    pass


class InjectionInput(InjectionCommon, graphene.InputObjectType):
    pass


class InjectionOutput(InjectionCommon, graphene.ObjectType):
    pass


class IniCommon:
    ini_string = graphene.String()


class IniInput(IniCommon, graphene.InputObjectType):
    pass


class IniOutput(IniCommon, graphene.ObjectType):
    pass


class LikelihoodCommon:
    pass


class LikelihoodInput(LikelihoodCommon, graphene.InputObjectType):
    pass


class LikelihoodOutput(LikelihoodCommon, graphene.ObjectType):
    pass


class PriorCommon:
    prior_default = graphene.String()


class PriorInput(PriorCommon, graphene.InputObjectType):
    pass


class PriorOutput(PriorCommon, graphene.ObjectType):
    pass


class PostProcessingCommon:
    pass


class PostProcessingInput(PostProcessingCommon, graphene.InputObjectType):
    pass


class PostProcessingOutput(PostProcessingCommon, graphene.ObjectType):
    pass


class SamplerCommon:
    nlive = graphene.Int()
    nact = graphene.Int()
    maxmcmc = graphene.Int()
    walks = graphene.Int()
    dlogz = graphene.Decimal()
    cpus = graphene.Int()
    sampler_choice = graphene.String()


class SamplerInput(SamplerCommon, graphene.InputObjectType):
    pass


class SamplerOutput(SamplerCommon, graphene.ObjectType):
    pass


class WaveformCommon:
    model = graphene.String()


class WaveformInput(WaveformCommon, graphene.InputObjectType):
    pass


class WaveformOutput(WaveformCommon, graphene.ObjectType):
    pass


class JobDetailsCommon:
    name = graphene.String()
    description = graphene.String()
    private = graphene.Boolean()


class JobDetailsInput(JobDetailsCommon, graphene.InputObjectType):
    cluster = graphene.String()


class JobDetailsOutput(graphene.ObjectType, JobDetailsCommon):
    pass


class JobParameterInput(graphene.InputObjectType):
    details = JobDetailsInput()

    # calibration = CalibrationInput()
    data = DataInput()
    detector = DetectorInput()
    # injection = InjectionInput()
    # likelihood = LikelihoodInput()
    prior = PriorInput()
    # post_processing = PostProcessingInput()
    sampler = SamplerInput()
    waveform = WaveformInput()


class JobParameterOutput(graphene.ObjectType):
    details = graphene.Field(JobDetailsOutput)

    # calibration = graphene.Field(CalibrationOutput)
    data = graphene.Field(DataOutput)
    detector = graphene.Field(DetectorOutput)
    # injection = graphene.Field(InjectionOutput)
    # likelihood = graphene.Field(LikelihoodOutput)
    prior = graphene.Field(PriorOutput)
    # post_processing = graphene.Field(PostProcessingOutput)
    sampler = graphene.Field(SamplerOutput)
    waveform = graphene.Field(WaveformOutput)


class JobIniInput(graphene.InputObjectType):
    details = JobDetailsInput()
    ini_string = IniInput()


class JobIniOutput(graphene.ObjectType):
    details = graphene.Field(JobDetailsOutput)
    ini_string = graphene.Field(IniOutput)


class SupportingFileUploadInput(graphene.InputObjectType):
    file_token = graphene.String()
    supporting_file = Upload(required=True)


class SupportingFileUploadResult(graphene.ObjectType):
    result = graphene.Boolean()
