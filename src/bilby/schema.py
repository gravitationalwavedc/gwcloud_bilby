import graphene
from graphene import ObjectType, relay, Connection, Int
from graphene_django.types import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django_filters import FilterSet, OrderingFilter

from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Prior, Sampler, SamplerParameter
from .views import create_bilby_job
from .types import OutputStartType, AbstractDataType, AbstractSignalType, AbstractSamplerType

from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id, to_global_id
from django.conf import settings


def parameter_resolvers(name):
    def func(parent, info):
        if parent.parameter.get(name=name).value in ['true', 'True']:
            return True
        elif parent.parameter.get(name=name).value in ['false', 'False']:
            return False
        else:
            return parent.parameter.get(name=name).value

    return func


# Used to give values to fields in a DjangoObjectType, if the fields were not present in the Django model
# Specifically used here to get values from the parameter models
def populate_fields(object_to_modify, field_list, resolver_func):
    for name in field_list:
        setattr(object_to_modify, 'resolve_{}'.format(name), staticmethod(resolver_func(name)))


class UserBilbyJobFilter(FilterSet):
    class Meta:
        model = BilbyJob
        fields = '__all__'

    order_by = OrderingFilter(
        fields=(
            ('last_updated', 'lastUpdated'),
            ('name', 'name'),
        )
    )

    @property
    def qs(self):
        return super(UserBilbyJobFilter, self).qs.filter(user_id=self.request.user.user_id)


class PublicBilbyJobFilter(FilterSet):
    class Meta:
        model = BilbyJob
        fields = '__all__'

    order_by = OrderingFilter(
        fields=(
            ('last_updated', 'last_updated'),
            ('name', 'name'),
        )
    )

    @property
    def qs(self):
        return super(PublicBilbyJobFilter, self).qs.filter(private=False)


class BilbyJobNode(DjangoObjectType):
    class Meta:
        model = BilbyJob
        convert_choices_to_enum = False
        interfaces = (relay.Node,)

    job_status = graphene.String()
    last_updated = graphene.String()
    start = graphene.Field(OutputStartType)

    # priors = graphene.Field(OutputPriorType)

    def resolve_last_updated(parent, info):
        return parent.last_updated.strftime("%d/%m/%Y, %H:%M:%S")

    def resolve_start(parent, info):
        return {
            "name": parent.name,
            "description": parent.description,
            "private": parent.private
        }

    # Couldn't do priors in the same way as the other things - It may require more though to restructure the models and frontend
    # def resolve_priors(parent, info):
    #     d = {}
    #     for prior in parent.prior.all():
    #         d.update({
    #             prior.name: {
    #                 "value": prior.fixed_value,
    #                 "type": prior.prior_choice,
    #                 "min": prior.uniform_min_value,
    #                 "max": prior.uniform_max_value
    #             }
    #         })

    #     return d


class DataType(DjangoObjectType, AbstractDataType):
    class Meta:
        model = Data
        interfaces = (relay.Node,)
        convert_choices_to_enum = False


populate_fields(
    DataType,
    [
        'hanford',
        'livingston',
        'virgo',
        'signal_duration',
        'sampling_frequency',
        'trigger_time',
        'hanford_minimum_frequency',
        'hanford_maximum_frequency',
        'hanford_channel',
        'livingston_minimum_frequency',
        'livingston_maximum_frequency',
        'livingston_channel',
        'virgo_minimum_frequency',
        'virgo_maximum_frequency',
        'virgo_channel',
    ],
    parameter_resolvers
)


class SignalType(DjangoObjectType, AbstractSignalType):
    class Meta:
        model = Signal
        interfaces = (relay.Node,)
        convert_choices_to_enum = False


populate_fields(
    SignalType,
    [
        'mass1',
        'mass2',
        'luminosity_distance',
        'psi',
        'iota',
        'phase',
        'merger_time',
        'ra',
        'dec'
    ],
    parameter_resolvers
)


class PriorType(DjangoObjectType):
    class Meta:
        model = Prior
        interfaces = (relay.Node,)
        convert_choices_to_enum = False

    def resolve_prior_choice(parent, info):
        return parent.prior_choice


# populate_fields(
#     PriorType,
#     [
#     #    'number'
#     ],
#     parameter_resolvers
# )

class SamplerType(DjangoObjectType, AbstractSamplerType):
    class Meta:
        model = Sampler
        interfaces = (relay.Node,)
        convert_choices_to_enum = False


populate_fields(
    SamplerType,
    [
        #    'number'
    ],
    parameter_resolvers
)


class UserDetails(ObjectType):
    username = graphene.String()

    def resolve_username(parent, info):
        return "Todo"


class BilbyResultFile(ObjectType):
    path = graphene.String()
    is_dir = graphene.Boolean()
    file_size = graphene.Int()
    download_id = graphene.String()


class BilbyResultFiles(ObjectType):
    class Meta:
        interfaces = (relay.Node,)

    class Input:
        job_id = graphene.ID()

    files = graphene.List(BilbyResultFile)


class Query(object):
    bilby_job = relay.Node.Field(BilbyJobNode)
    bilby_jobs = DjangoFilterConnectionField(BilbyJobNode, filterset_class=UserBilbyJobFilter)
    public_bilby_jobs = DjangoFilterConnectionField(BilbyJobNode, filterset_class=PublicBilbyJobFilter)

    data = graphene.Field(DataType, data_id=graphene.String())
    all_data = graphene.List(DataType)

    bilby_result_files = graphene.Field(BilbyResultFiles, job_id=graphene.ID(required=True))

    gwclouduser = graphene.Field(UserDetails)

    @login_required
    def resolve_gwclouduser(self, info, **kwargs):
        return info.context.user

    @login_required
    def resolve_bilby_result_files(self, info, **kwargs):
        # Get the model id of the bilby job
        _, job_id = from_global_id(kwargs.get("job_id"))

        # Try to look up the job with the id provided
        job = BilbyJob.objects.get(id=job_id)

        # Can only get the file list if the job is public or the user owns the job
        if not job.private or info.context.user.user_id == job.user_id:
            # Fetch the file list from the job controller
            success, files = job.get_file_list()
            if not success:
                raise Exception("Error getting file list. " + str(files))

            # Build the resulting file list and send it back to the client
            result = []
            for f in files:
                download_id = ""
                if not f["isDir"]:
                    # todo: Optimize how file download ids are generated. An id for every file every time
                    # todo: the page is loaded is not effective at all
                    # Create a file download id for this file
                    success, download_id = job.get_file_download_id(f["path"])
                    if not success:
                        raise Exception("Error creating file download url. " + str(download_id))

                result.append(
                    BilbyResultFile(
                        path=f["path"],
                        is_dir=f["isDir"],
                        file_size=f["fileSize"],
                        download_id=download_id
                    )
                )

            return BilbyResultFiles(files=result)

        raise Exception("Permission Denied")


class StartInput(graphene.InputObjectType):
    name = graphene.String()
    description = graphene.String()
    private = graphene.Boolean()


class DataInput(graphene.InputObjectType, AbstractDataType):
    data_choice = graphene.String()


class SignalInput(graphene.InputObjectType, AbstractSignalType):
    signal_choice = graphene.String()
    signal_model = graphene.String()


class PriorInput(graphene.InputObjectType):
    prior_choice = graphene.String()


class SamplerInput(graphene.InputObjectType, AbstractSamplerType):
    sampler_choice = graphene.String()


class BilbyJobCreationResult(ObjectType):
    job_id = graphene.String()


class BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        start = StartInput()
        data = DataInput()
        signal = SignalInput()
        prior = PriorInput()
        sampler = SamplerInput()

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, start, data, signal, prior, sampler):
        # Create the bilby job
        job_id = create_bilby_job(info.context.user.user_id, start, data, signal, prior, sampler)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", job_id)

        # Return the bilby job id to the client
        return BilbyJobMutation(
            result=BilbyJobCreationResult(job_id=job_id)
        )


class UniqueNameMutation(relay.ClientIDMutation):
    class Input:
        name = graphene.String()

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, name):

        return UniqueNameMutation(result=name)


class Mutation(graphene.ObjectType):
    new_bilby_job = BilbyJobMutation.Field()
    is_name_unique = UniqueNameMutation.Field()
