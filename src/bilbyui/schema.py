from decimal import Decimal

import graphene
from django_filters import FilterSet, OrderingFilter
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphene_django.types import DjangoObjectType
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id, to_global_id

from .models import BilbyJob, Label
from .status import JobStatus
from .types import JobStatusType, BilbyJobCreationResult, JobParameterInput, JobParameterOutput
from .utils.db_search.db_search import perform_db_search
from .utils.derive_job_status import derive_job_status
from .utils.gen_parameter_output import generate_parameter_output
from .utils.jobs.request_job_filter import request_job_filter
from .views import create_bilby_job, update_bilby_job, create_bilby_job_from_ini_string


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
        return BilbyJob.user_bilby_job_filter(super(UserBilbyJobFilter, self).qs, self)


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
        return BilbyJob.public_bilby_job_filter(super(PublicBilbyJobFilter, self).qs, self)


class BilbyJobNode(DjangoObjectType):
    class Meta:
        model = BilbyJob
        convert_choices_to_enum = False
        interfaces = (relay.Node,)

    job_status = graphene.Field(JobStatusType)
    last_updated = graphene.String()
    params = graphene.Field(JobParameterOutput)
    labels = graphene.List(LabelType)

    @classmethod
    def get_queryset(parent, queryset, info):
        return BilbyJob.bilby_job_filter(queryset, info)

    def resolve_last_updated(parent, info):
        return parent.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")

    def resolve_params(parent, info):
        return generate_parameter_output(parent)

    def resolve_labels(parent, info):
        return parent.labels.all()

    def resolve_job_status(parent, info):
        try:
            # Get job details from the job controller
            _, jc_jobs = request_job_filter(
                info.context.user.user_id,
                ids=[parent.job_controller_id]
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


class UserDetails(graphene.ObjectType):
    username = graphene.String()

    def resolve_username(parent, info):
        return "Todo"


class BilbyResultFile(graphene.ObjectType):
    path = graphene.String()
    is_dir = graphene.Boolean()
    file_size = graphene.Decimal()
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
        return Label.all()

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
                    labels=BilbyJob.get_by_id(job['job']['id'], info.context.user).labels.all(),
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
        job = BilbyJob.get_by_id(job_id, info.context.user)

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
                    file_size=Decimal(f["fileSize"]),
                    download_id=download_id
                )
            )

        return BilbyResultFiles(files=result)


class BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        params = JobParameterInput()

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, params):
        user = info.context.user

        # Check user is authenticated
        if not user.is_authenticated:
            raise GraphQLError('You do not have permission to perform this action')

        # Create the bilby job
        bilby_job = create_bilby_job(user, params)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobMutation(
            result=BilbyJobCreationResult(job_id=job_id)
        )


class BilbyJobFromIniStringMutation(relay.ClientIDMutation):
    class Input:
        # start = StartInput()
        ini_string = graphene.String()

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, start, ini_string):
        user = info.context.user

        # Check user is authenticated
        if not user.is_authenticated:
            raise GraphQLError('You do not have permission to perform this action')

        # Create the bilby job
        bilby_job = create_bilby_job_from_ini_string(user, start, ini_string)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobFromIniStringMutation(
            result=job_id
        )


class UpdateBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        job_id = graphene.ID(required=True)
        private = graphene.Boolean(required=False)
        labels = graphene.List(graphene.String, required=False)

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        # Check user is authenticated
        if not user.is_authenticated:
            raise GraphQLError('You do not have permission to perform this action')

        job_id = kwargs.pop("job_id")

        # Update privacy of bilby job
        message = update_bilby_job(from_global_id(job_id)[1], user, **kwargs)

        # Return the bilby job id to the client
        return UpdateBilbyJobMutation(
            result=message
        )


class Mutation(graphene.ObjectType):
    new_bilby_job = BilbyJobMutation.Field()
    new_bilby_job_from_ini_string = BilbyJobFromIniStringMutation.Field()
    update_bilby_job = UpdateBilbyJobMutation.Field()
