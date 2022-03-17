from decimal import Decimal

from django.conf import settings
from django_filters import FilterSet, OrderingFilter
import graphene
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphene_django.types import DjangoObjectType
from graphene_file_upload.scalars import Upload
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id, to_global_id

from .models import BilbyJob, BilbyJobUploadToken, EventID, FileDownloadToken, Label, SupportingFile
from .status import JobStatus
from .types import (
    BilbyJobCreationResult,
    JobDetailsInput,
    JobIniInput,
    JobParameterInput,
    JobParameterOutput,
    JobStatusType, BilbyJobSupportingFile, SupportingFileUploadResult,
)
from .utils.auth.lookup_users import request_lookup_users
from .utils.db_search.db_search import perform_db_search
from .utils.derive_job_status import derive_job_status
from .utils.gen_parameter_output import generate_parameter_output
from .utils.jobs.request_file_download_id import request_file_download_ids
from .utils.jobs.request_job_filter import request_job_filter
from .views import (
    create_bilby_job,
    create_bilby_job_from_ini_string,
    create_event_id,
    delete_event_id,
    update_bilby_job,
    update_event_id,
    upload_bilby_job, upload_supporting_file,
)


class LabelType(DjangoObjectType):
    class Meta:
        model = Label
        interfaces = (relay.Node,)


class EventIDType(DjangoObjectType):
    class Meta:
        model = EventID
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

    user = graphene.String()
    job_status = graphene.Field(JobStatusType)
    last_updated = graphene.String()
    params = graphene.Field(JobParameterOutput)
    labels = graphene.List(LabelType)
    event_id = graphene.Field(EventIDType)

    @classmethod
    def get_queryset(parent, queryset, info):
        return BilbyJob.bilby_job_filter(queryset, info)

    def resolve_user(parent, info):
        success, users = request_lookup_users([2], info.context.user.user_id)
        if success and users:
            return f"{users[0]['firstName']} {users[0]['lastName']}"
        return "Unknown User"

    def resolve_last_updated(parent, info):
        return parent.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")

    def resolve_params(parent, info):
        return generate_parameter_output(parent)

    def resolve_labels(parent, info):
        return parent.labels.all()

    def resolve_event_id(parent, info):
        return parent.event_id

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
    event_id = graphene.Field(EventIDType)
    labels = graphene.List(LabelType)
    description = graphene.String()
    timestamp = graphene.String()
    id = graphene.ID()


class BilbyPublicJobConnection(relay.Connection):
    class Meta:
        node = BilbyPublicJobNode


class AllLabelsConnection(relay.Connection):
    class Meta:
        node = LabelType


class GenerateBilbyJobUploadToken(graphene.ObjectType):
    token = graphene.String()


class Query(object):
    bilby_job = relay.Node.Field(BilbyJobNode)
    bilby_jobs = DjangoFilterConnectionField(BilbyJobNode, filterset_class=UserBilbyJobFilter)
    public_bilby_jobs = relay.ConnectionField(
        BilbyPublicJobConnection,
        search=graphene.String(),
        time_range=graphene.String()
    )

    all_labels = relay.ConnectionField(
       AllLabelsConnection
    )

    event_id = graphene.Field(EventIDType, event_id=graphene.String(required=True))
    all_event_ids = graphene.List(EventIDType)

    bilby_result_files = graphene.Field(BilbyResultFiles, job_id=graphene.ID(required=True))

    gwclouduser = graphene.Field(UserDetails)

    generate_bilby_job_upload_token = graphene.Field(GenerateBilbyJobUploadToken)

    @login_required
    def resolve_generate_bilby_job_upload_token(self, info, **kwargs):
        user = info.context.user

        # Create a job upload token
        token = BilbyJobUploadToken.create(user)

        # Return the generated token
        return GenerateBilbyJobUploadToken(token=str(token.token))

    @login_required
    def resolve_all_labels(self, info, **kwargs):
        return Label.all()

    @login_required
    def resolve_event_id(self, info, event_id):
        return EventID.get_by_event_id(event_id=event_id, user=info.context.user)

    @login_required
    def resolve_all_event_ids(self, info, **kwargs):
        return EventID.filter_by_ligo(is_ligo=info.context.user.is_ligo)

    @login_required
    def resolve_public_bilby_jobs(self, info, **kwargs):
        # Perform the database search
        success, jobs = perform_db_search(info.context.user, kwargs)

        if not success:
            return []

        # Parse the result in to graphql objects
        result = []

        for job in jobs:
            bilby_job = BilbyJob.get_by_id(job['job']['id'], info.context.user)

            result.append(
                BilbyPublicJobNode(
                    user=f"{job['user']['firstName']} {job['user']['lastName']}",
                    name=job['job']['name'],
                    description=job['job']['description'],
                    job_status=JobStatusType(
                        name=JobStatus.display_name(
                            JobStatus.COMPLETED if bilby_job.is_uploaded_job else job['history'][0]['state']
                        ),
                        number=JobStatus.COMPLETED if bilby_job.is_uploaded_job else job['history'][0]['state'],
                        date=bilby_job.creation_time if bilby_job.is_uploaded_job else job['history'][0]['timestamp']
                    ),
                    event_id=EventIDType.get_node(info, id=bilby_job.event_id.id) if bilby_job.event_id else None,
                    labels=bilby_job.labels.all(),
                    timestamp=bilby_job.creation_time if bilby_job.is_uploaded_job else job['history'][0]['timestamp'],
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


class EventIDMutation(relay.ClientIDMutation):
    class Input:
        event_id = graphene.String(required=True)
        trigger_id = graphene.String()
        nickname = graphene.String()
        is_ligo_event = graphene.Boolean()

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        if user.user_id not in settings.PERMITTED_EVENT_CREATION_USER_IDS:
            raise Exception('User is not permitted to create EventIDs')

        message = create_event_id(user, **kwargs)

        return EventIDMutation(
            result=message
        )


class UpdateEventIDMutation(relay.ClientIDMutation):
    class Input:
        event_id = graphene.String(required=True)
        trigger_id = graphene.String()
        nickname = graphene.String()
        is_ligo_event = graphene.Boolean()

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        if user.user_id not in settings.PERMITTED_EVENT_CREATION_USER_IDS:
            raise Exception('User is not permitted to modify EventIDs')

        message = update_event_id(user, **kwargs)

        return UpdateEventIDMutation(
            result=message
        )


class DeleteEventIDMutation(relay.ClientIDMutation):
    class Input:
        event_id = graphene.String(required=True)

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, event_id):
        user = info.context.user

        if user.user_id not in settings.PERMITTED_EVENT_CREATION_USER_IDS:
            raise Exception('User is not permitted to delete EventIDs')

        message = delete_event_id(user, event_id)

        return DeleteEventIDMutation(
            result=message
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
        bilby_job, supporting_file_details = create_bilby_job_from_ini_string(user, params)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        files = [
            BilbyJobSupportingFile(
                file_path=f['file_path'],
                token=f['token']
            ) for f in supporting_file_details
        ]

        # Return the bilby job id to the client
        return BilbyJobFromIniStringMutation(
            result=BilbyJobCreationResult(
                job_id=job_id,
                supporting_files=files
            )
        )


class UpdateBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        job_id = graphene.ID(required=True)
        private = graphene.Boolean(required=False)
        labels = graphene.List(graphene.String, required=False)
        event_id = graphene.String(required=False)
        description = graphene.String(required=False)
        name = graphene.String(required=False)

    result = graphene.String()
    job_id = graphene.ID()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        job_id = kwargs.pop("job_id")

        # Update privacy of bilby job
        message = update_bilby_job(from_global_id(job_id)[1], user, **kwargs)

        # Return the bilby job id to the client
        return UpdateBilbyJobMutation(
            result=message, job_id=job_id
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
        upload_token = graphene.String()
        details = JobDetailsInput()
        job_file = Upload(required=True)

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, upload_token, details, job_file):
        # Get the token being used to perform the upload - this will return None if the token doesn't exist or
        # is expired
        token = BilbyJobUploadToken.get_by_token(upload_token)
        if not token:
            raise GraphQLError("Job upload token is invalid or expired.")

        # Try uploading the bilby job
        bilby_job = upload_bilby_job(token, details, job_file)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobMutation(
            result=BilbyJobCreationResult(job_id=job_id)
        )


class UploadSupportingFileMutation(relay.ClientIDMutation):
    class Input:
        file_token = graphene.String()
        supporting_file = Upload(required=True)

    result = graphene.Field(SupportingFileUploadResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, file_token, supporting_file):
        # Get the token being used to perform the upload - this will return None if the token doesn't exist or
        # if the bilby job is expired
        token = SupportingFile.get_by_upload_token(file_token)
        if not token:
            raise GraphQLError("Supporting file upload token is invalid or expired.")

        # Try uploading the bilby job supporting file
        success = upload_supporting_file(token, supporting_file)

        # Return the success state job id to the client
        return UploadSupportingFileMutation(
            result=SupportingFileUploadResult(
                result=success
            )
        )


class Mutation(graphene.ObjectType):
    new_bilby_job = BilbyJobMutation.Field()
    new_bilby_job_from_ini_string = BilbyJobFromIniStringMutation.Field()
    update_bilby_job = UpdateBilbyJobMutation.Field()
    generate_file_download_ids = GenerateFileDownloadIds.Field()
    upload_bilby_job = UploadBilbyJobMutation.Field()
    create_event_id = EventIDMutation.Field()
    update_event_id = UpdateEventIDMutation.Field()
    delete_event_id = DeleteEventIDMutation.Field()
    upload_supporting_file = UploadSupportingFileMutation.Field()
