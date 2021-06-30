from decimal import Decimal

import graphene
from django.conf import settings
from django_filters import FilterSet, OrderingFilter
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphene_django.types import DjangoObjectType
from graphene_file_upload.scalars import Upload
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id, to_global_id

from .models import BilbyJob, Label, FileDownloadToken
from .status import JobStatus
from .types import JobStatusType, BilbyJobCreationResult, JobParameterInput, JobParameterOutput, JobIniInput, \
    JobDetailsInput
from .utils.db_search.db_search import perform_db_search
from .utils.derive_job_status import derive_job_status
from .utils.gen_parameter_output import generate_parameter_output
from .utils.jobs.request_file_download_id import request_file_download_ids
from .utils.jobs.request_job_filter import request_job_filter
from .views import create_bilby_job, update_bilby_job, create_bilby_job_from_ini_string, upload_bilby_job


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
        # Uploaded jobs are always complete
        if parent.is_uploaded_job:
            return {
                "name": JobStatus.display_name(JobStatus.COMPLETED),
                "number": JobStatus.COMPLETED,
                "date": parent.creation_time
            }

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
    download_token = graphene.String()


class BilbyResultFiles(graphene.ObjectType):
    class Meta:
        interfaces = (relay.Node,)

    class Input:
        job_id = graphene.ID()

    files = graphene.List(BilbyResultFile)
    is_uploaded_job = graphene.Boolean()


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

        # Generate download tokens for the list of files
        paths = [f['path'] for f in filter(lambda x: not x['isDir'], files)]
        tokens = FileDownloadToken.create(job, paths)

        # Generate a dict that can be used to query the generated tokens
        token_dict = {tk.path: tk.token for tk in tokens}

        # Build the resulting file list and send it back to the client
        result = [
            BilbyResultFile(
                path=f["path"],
                is_dir=f["isDir"],
                file_size=Decimal(f["fileSize"]),
                download_token=token_dict[f["path"]] if f["path"] in token_dict else None
            )
            for f in files
        ]

        return BilbyResultFiles(
            files=result,
            is_uploaded_job=job.is_uploaded_job
        )


class BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        params = JobParameterInput()

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, params):
        user = info.context.user

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
        params = JobIniInput()

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, params):
        user = info.context.user

        # Create the bilby job
        bilby_job = create_bilby_job_from_ini_string(user, params)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobFromIniStringMutation(
            result=BilbyJobCreationResult(job_id=job_id)
        )


class UpdateBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        job_id = graphene.ID(required=True)
        private = graphene.Boolean(required=False)
        labels = graphene.List(graphene.String, required=False)

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        job_id = kwargs.pop("job_id")

        # Update privacy of bilby job
        message = update_bilby_job(from_global_id(job_id)[1], user, **kwargs)

        # Return the bilby job id to the client
        return UpdateBilbyJobMutation(
            result=message
        )


class GenerateFileDownloadIds(relay.ClientIDMutation):
    class Input:
        job_id = graphene.ID(required=True)
        download_tokens = graphene.List(graphene.String, required=True)

    result = graphene.List(graphene.String)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, job_id, download_tokens):
        user = info.context.user

        # Get the job these file downloads are for
        job = BilbyJob.get_by_id(from_global_id(job_id)[1], user)

        # Verify the download tokens and get the paths
        paths = FileDownloadToken.get_paths(job, download_tokens)

        # Check that all tokens were found
        if None in paths:
            raise GraphQLError("At least one token was invalid or expired.")

        # For uploaded jobs, we can just return the exact some download tokens - this function is basically a no-op
        # for uploaded jobs
        if job.is_uploaded_job:
            return GenerateFileDownloadIds(
                result=download_tokens
            )

        # Request the list of file download ids from the list of paths
        # Only the original job author may generate a file download id
        success, result = request_file_download_ids(
            job,
            paths
        )

        # Report the error if there is one
        if not success:
            raise GraphQLError(result)

        # Return the list of file download ids
        return GenerateFileDownloadIds(
            result=result
        )


class UploadBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        details = JobDetailsInput()
        job_file = Upload(required=True)

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, details, job_file):
        user = info.context.user

        if user.user_id not in settings.PERMITTED_UPLOAD_USER_IDS:
            raise Exception("User is not permitted to upload jobs")

        # Try uploading the bilby job
        bilby_job = upload_bilby_job(user, details, job_file)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobMutation(
            result=BilbyJobCreationResult(job_id=job_id)
        )


class Mutation(graphene.ObjectType):
    new_bilby_job = BilbyJobMutation.Field()
    new_bilby_job_from_ini_string = BilbyJobFromIniStringMutation.Field()
    update_bilby_job = UpdateBilbyJobMutation.Field()
    generate_file_download_ids = GenerateFileDownloadIds.Field()
    upload_bilby_job = UploadBilbyJobMutation.Field()
