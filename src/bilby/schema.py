import graphene
from graphene import ObjectType, relay, Connection, Int
from graphene_django.types import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
import django_filters

from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Prior, Sampler, SamplerParameter
from .views import create_bilby_job

from graphql_jwt.decorators import login_required

from django.conf import settings


class UserBilbyJobFilter(django_filters.FilterSet):
    class Meta:
        model = BilbyJob
        fields = ['name']

    @property
    def qs(self):
        return super(UserBilbyJobFilter, self).qs.filter(user_id=self.request.user.user_id)


class BilbyJobNode(DjangoObjectType):
    class Meta:
        model = BilbyJob
        filter_fields = ['name', 'username']
        #filterset_class = UserBilbyJobFilter
        interfaces = (relay.Node, )

class BilbyJobConnection(Connection):
    class Meta:
        node = BilbyJobNode
    count = Int()

    def resolve_count(root, info):
        return len(root.edges)

class DataType(DjangoObjectType):
    class Meta:
        model = Data

class DataParameterType(DjangoObjectType):
    class Meta:
        model = DataParameter

class SignalType(DjangoObjectType):
    class Meta:
        model = Signal

class SignalParameterType(DjangoObjectType):
    class Meta:
        model = SignalParameter

class PriorType(DjangoObjectType):
    class Meta:
        model = Prior

class SamplerType(DjangoObjectType):
    class Meta:
        model = Sampler

class SamplerParameterType(DjangoObjectType):
    class Meta:
        model = SamplerParameter

class UserDetails(ObjectType):
    username = graphene.String()


class Query(object):
    bilby_job = graphene.Field(BilbyJobNode, job_id=graphene.String())
    bilby_jobs = DjangoFilterConnectionField(BilbyJobNode)

    data = graphene.Field(DataType, data_id=graphene.String())
    all_data = graphene.List(DataType)

    # def resolve_bilby_job(self, info, job_id):
    #     return BilbyJob.objects.get(pk=job_id)
    
    # def resolve_bilby_jobs(self, info, **kwargs):
    #     return BilbyJob.objects.all()
    
    def resolve_data(self, info, data_id):
        return Data.objects.get(pk=data_id)

    def resolve_all_data(self, info, **kwargs):
        return Data.objects.all()

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
        print(info.context.user.__dict__)
        return Hello(kwargs['message'])


class StartInput(graphene.InputObjectType):
    job_name = graphene.String()
    job_description = graphene.String()

class DataInput(graphene.InputObjectType):
    data_type = graphene.String()
    hanford = graphene.Boolean()
    livingston = graphene.Boolean()
    virgo = graphene.Boolean()
    signal_duration = graphene.String()
    sampling_frequency = graphene.String()
    start_time = graphene.String()

class SignalInput(graphene.InputObjectType):
    signal_type = graphene.String()
    signal_model = graphene.String()
    mass1 = graphene.String()
    mass2 = graphene.String()
    luminosity_distance = graphene.String()
    psi = graphene.String()
    iota = graphene.String()
    phase = graphene.String()
    merger_time = graphene.String()
    ra = graphene.String()
    dec = graphene.String()

class PriorStructureInput(graphene.InputObjectType):
    type = graphene.String()
    value = graphene.String()
    min = graphene.String()
    max = graphene.String()

class PriorInput(graphene.InputObjectType):
    mass1 = graphene.InputField(PriorStructureInput)
    mass2 = graphene.InputField(PriorStructureInput)
    luminosity_distance = graphene.InputField(PriorStructureInput)
    psi = graphene.InputField(PriorStructureInput)
    iota = graphene.InputField(PriorStructureInput)
    phase = graphene.InputField(PriorStructureInput)
    merger_time = graphene.InputField(PriorStructureInput)
    ra = graphene.InputField(PriorStructureInput)
    dec = graphene.InputField(PriorStructureInput)

class SamplerInput(graphene.InputObjectType):
    sampler = graphene.String()
    number = graphene.String()
    

class BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        start = StartInput()
        data = DataInput()
        signal = SignalInput()
        prior = PriorInput()
        sampler = SamplerInput()

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, start, data, signal, prior, sampler):
        print(info.context.user)
        create_bilby_job(info.context.user.user_id, info.context.user.username, start, data, signal, prior, sampler)

        return BilbyJobMutation(result='Job created')

class Mutation(graphene.ObjectType):
    hello = Hello.Field()
    new_bilby_job = BilbyJobMutation.Field()
