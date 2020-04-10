import graphene
from graphene import ObjectType, relay, Connection, Int
from graphene_django.types import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django_filters import FilterSet, OrderingFilter

from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Prior, Sampler, SamplerParameter
from .views import create_bilby_job
from .types import OutputStartType, AbstractDataType, AbstractSignalType, OutputPriorType, OutputPriorStructureType, InputPriorType, AbstractSamplerType

from graphql_jwt.decorators import login_required

from django.conf import settings

def parameter_resolvers(name):
    def func(parent, info):
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
            ('last_updated', 'last_updated'),
            ('name', 'name'),
        )
    )

    @property
    def qs(self):
        return super(UserBilbyJobFilter, self).qs.filter(user_id=self.request.user.user_id)

class BilbyJobNode(DjangoObjectType):
    class Meta:
        model = BilbyJob
        convert_choices_to_enum = False
        interfaces = (relay.Node, )
        filterset_class = UserBilbyJobFilter

    last_updated = graphene.String()
    start = graphene.Field(OutputStartType)
    priors = graphene.Field(OutputPriorType)

    def resolve_last_updated(parent, info):
        return parent.last_updated.strftime("%d/%m/%Y, %H:%M:%S")

    def resolve_start(parent, info):
        return {
            "name": parent.name,
            "description": parent.description,
        }

    # Couldn't do priors in the same way as the other things - It may require more though to restructure the models and frontend
    def resolve_priors(parent, info):
        d = {}
        for prior in parent.prior.all():
            d.update({
                prior.name : {
                    "value": prior.fixed_value,
                    "type": prior.prior_choice,
                    "min": prior.uniform_min_value,
                    "max": prior.uniform_max_value
                }
            })

        return d

class DataType(DjangoObjectType, AbstractDataType):
    class Meta:
        model = Data
        interfaces = (relay.Node,)
        convert_choices_to_enum = False

populate_fields(DataType, ['hanford', 'livingston', 'virgo', 'signal_duration', 'sampling_frequency', 'start_time'], parameter_resolvers)


class SignalType(DjangoObjectType, AbstractSignalType):
    class Meta:
        model = Signal
        interfaces = (relay.Node,)
        convert_choices_to_enum = False

populate_fields(SignalType, ['mass1', 'mass2', 'luminosity_distance', 'psi', 'iota', 'phase', 'merger_time', 'ra', 'dec'], parameter_resolvers)


class SamplerType(DjangoObjectType, AbstractSamplerType):
    class Meta:
        model = Sampler
        interfaces = (relay.Node,)
        convert_choices_to_enum = False

populate_fields(SamplerType, ['number'], parameter_resolvers)



class UserDetails(ObjectType):
    username = graphene.String()
    


class Query(object):
    bilby_job = relay.Node.Field(BilbyJobNode)
    bilby_jobs = DjangoFilterConnectionField(BilbyJobNode)

    data = graphene.Field(DataType, data_id=graphene.String())
    all_data = graphene.List(DataType)

    gwclouduser = graphene.Field(UserDetails)

    @login_required
    def resolve_gwclouduser(self, info, **kwargs):
        return info.context.user


class Hello(graphene.relay.ClientIDMutation):
    class Input:
        message = graphene.String(required=True)

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, **kwargs):
        return Hello(kwargs['message'])


class StartInput(graphene.InputObjectType):
    name = graphene.String()
    description = graphene.String()

class DataInput(graphene.InputObjectType, AbstractDataType):
    data_choice = graphene.String()

class SignalInput(graphene.InputObjectType, AbstractSignalType):
    signal_choice = graphene.String()
    signal_model = graphene.String()

# class PriorStructureInput(graphene.InputObjectType):
#     type = graphene.String()
#     value = graphene.String()
#     min = graphene.String()
#     max = graphene.String()

# class PriorInput(graphene.InputObjectType):
#     mass1 = graphene.InputField(PriorStructureInput)
#     mass2 = graphene.InputField(PriorStructureInput)
#     luminosity_distance = graphene.InputField(PriorStructureInput)
#     psi = graphene.InputField(PriorStructureInput)
#     iota = graphene.InputField(PriorStructureInput)
#     phase = graphene.InputField(PriorStructureInput)
#     merger_time = graphene.InputField(PriorStructureInput)
#     ra = graphene.InputField(PriorStructureInput)
#     dec = graphene.InputField(PriorStructureInput)

class SamplerInput(graphene.InputObjectType, AbstractSamplerType):
    sampler_choice = graphene.String()


class BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        start = StartInput()
        data = DataInput()
        signal = SignalInput()
        prior = InputPriorType()
        sampler = SamplerInput()

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, start, data, signal, prior, sampler):
        print(info.context.user.user_id, info.context.user.username)
        create_bilby_job(info.context.user.user_id, info.context.user.username, start, data, signal, prior, sampler)

        return BilbyJobMutation(result='Job created')

class Mutation(graphene.ObjectType):
    hello = Hello.Field()
    new_bilby_job = BilbyJobMutation.Field()
