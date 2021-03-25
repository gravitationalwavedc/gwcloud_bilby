import graphene
from django_filters import FilterSet, OrderingFilter
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphene_django.types import DjangoObjectType
from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id, to_global_id

from .models import BilbyJob, Data, Signal, Prior, Sampler, Label
from .status import JobStatus
from .types import OutputStartType, AbstractDataType, AbstractSignalType, AbstractSamplerType, JobStatusType
from .utils.db_search.db_search import perform_db_search
from .utils.derive_job_status import derive_job_status
from .utils.jobs.request_job_filter import request_job_filter
from .views import create_bilby_job, update_bilby_job


def parameter_resolvers(name):
    def func(parent, info):
        try:
            param = parent.parameter.get(name=name)
            if param.value in ['true', 'True']:
                return True
            elif param.value in ['false', 'False']:
                return False
            else:
                return param.value

        except parent.parameter.model.DoesNotExist:
            return None

    return func


# Used to give values to fields in a DjangoObjectType, if the fields were not present in the Django model
# Specifically used here to get values from the parameter models
def populate_fields(object_to_modify, field_list, resolver_func):
    for name in field_list:
        setattr(object_to_modify, 'resolve_{}'.format(name), staticmethod(resolver_func(name)))


class LabelType(DjangoObjectType):
    class Meta:
        model = Label
        interfaces = (relay.Node,)


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

    job_status = graphene.Field(JobStatusType)
    last_updated = graphene.String()
    start = graphene.Field(OutputStartType)
    labels = graphene.List(LabelType)

    # priors = graphene.Field(OutputPriorType)

    @classmethod
    def get_queryset(parent, queryset, info):
        if info.context.user.is_anonymous:
            raise Exception("You must be logged in to perform this action.")
        # Users may not view ligo jobs if they are not a ligo user
        if info.context.user.is_ligo:
            return queryset
        else:
            return queryset.exclude(is_ligo_job=True)

    def resolve_last_updated(parent, info):
        return parent.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")

    def resolve_start(parent, info):
        return {
            "name": parent.name,
            "description": parent.description,
            "private": parent.private
        }

    def resolve_labels(parent, info):
        return parent.labels.all()

    def resolve_job_status(parent, info):
        try:
            # Get job details from the job controller
            _, jc_jobs = request_job_filter(
                info.context.user.user_id,
                ids=[parent.job_id]
            )

            status_number, status_name, status_date = derive_job_status(jc_jobs[0]["history"])

            return {
                "name": status_name,
                "number": status_number,
                "date": status_date.strftime("%Y-%m-%d %H:%M:%S UTC")
            }
        except Exception:
            return {
                "name": "Unknown",
                "number": 0,
                "data": "Unknown"
            }


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


class SamplerType(DjangoObjectType, AbstractSamplerType):
    class Meta:
        model = Sampler
        interfaces = (relay.Node,)
        convert_choices_to_enum = False


populate_fields(
    SamplerType,
    [
           'nlive',
           'nact',
           'maxmcmc',
           'walks',
           'dlogz',
           'cpus',
    ],
    parameter_resolvers
)


class UserDetails(graphene.ObjectType):
    username = graphene.String()

    def resolve_username(parent, info):
        return "Todo"


class BilbyResultFile(graphene.ObjectType):
    path = graphene.String()
    is_dir = graphene.Boolean()
    file_size = graphene.Int()
    download_id = graphene.String()


class BilbyResultFiles(graphene.ObjectType):
    class Meta:
        interfaces = (relay.Node,)

    class Input:
        job_id = graphene.ID()

    files = graphene.List(BilbyResultFile)


class BilbyPublicJobNode(graphene.ObjectType):
    user = graphene.String()
    name = graphene.String()
    job_status = graphene.Field(JobStatusType)
    labels = graphene.List(LabelType)
    description = graphene.String()
    timestamp = graphene.String()
    id = graphene.ID()


class BilbyPublicJobConnection(relay.Connection):
    class Meta:
        node = BilbyPublicJobNode


class Query(object):
    bilby_job = relay.Node.Field(BilbyJobNode)
    bilby_jobs = DjangoFilterConnectionField(BilbyJobNode, filterset_class=UserBilbyJobFilter)
    public_bilby_jobs = relay.ConnectionField(
        BilbyPublicJobConnection,
        search=graphene.String(),
        time_range=graphene.String()
    )

    all_labels = graphene.List(LabelType)

    bilby_result_files = graphene.Field(BilbyResultFiles, job_id=graphene.ID(required=True))

    gwclouduser = graphene.Field(UserDetails)

    @login_required
    def resolve_all_labels(self, info, **kwargs):
        return Label.objects.all()

    @login_required
    def resolve_public_bilby_jobs(self, info, **kwargs):
        # Perform the database search
        success, jobs = perform_db_search(info.context.user, kwargs)
        if not success:
            return []

        # Parse the result in to graphql objects
        result = []
        for job in jobs:
            result.append(
                BilbyPublicJobNode(
                    user=f"{job['user']['firstName']} {job['user']['lastName']}",
                    name=job['job']['name'],
                    description=job['job']['description'],
                    job_status=JobStatusType(
                        name=JobStatus.display_name(job['history'][0]['state']),
                        number=job['history'][0]['state'],
                        date=job['history'][0]['timestamp']
                    ),
                    labels=BilbyJob.objects.get(id=job['job']['id']).labels.all(),
                    timestamp=job['history'][0]['timestamp'],
                    id=to_global_id("BilbyJobNode", job['job']['id'])
                )
            )

        # Nb. The perform_db_search function currently requests one extra record than kwargs['first'].
        # This triggers the ArrayConnection used by returning the result array to correctly set
        # hasNextPage correctly, such that infinite scroll works as expected.
        return result

    @login_required
    def resolve_gwclouduser(self, info, **kwargs):
        return info.context.user

    @login_required
    def resolve_bilby_result_files(self, info, **kwargs):
        # Get the model id of the bilby job
        _, job_id = from_global_id(kwargs.get("job_id"))

        # Try to look up the job with the id provided
        job = BilbyJob.objects.get(id=job_id)

        # Ligo jobs may only be accessed by ligo users
        if job.is_ligo_job and not info.context.user.is_ligo:
            raise Exception("Permission Denied")

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


class BilbyJobCreationResult(graphene.ObjectType):
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
        job_id = create_bilby_job(info.context.user, start, data, signal, prior, sampler)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", job_id)

        # Return the bilby job id to the client
        return BilbyJobMutation(
            result=BilbyJobCreationResult(job_id=job_id)
        )


class UpdateBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        job_id = graphene.ID(required=True)
        private = graphene.Boolean(required=False)
        labels = graphene.List(graphene.String, required=False)

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, **kwargs):
        job_id = kwargs.pop("job_id")

        # Update privacy of bilby job
        message = update_bilby_job(from_global_id(job_id)[1], info.context.user.user_id, **kwargs)

        # Return the bilby job id to the client
        return UpdateBilbyJobMutation(
            result=message
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
    update_bilby_job = UpdateBilbyJobMutation.Field()
    is_name_unique = UniqueNameMutation.Field()
