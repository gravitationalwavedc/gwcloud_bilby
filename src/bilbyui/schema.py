import logging
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

from .constants import BilbyJobType
from .models import (
    BilbyJob,
    BilbyJobUploadToken,
    EventID,
    ExternalBilbyJob,
    FileDownloadToken,
    Label,
    SupportingFile,
)
from .services.event_ids import get_event_id, list_event_ids_for_user
from .services.jobs import get_job, list_public_jobs, update_job
from .services.labels import list_labels
from .status import JobStatus
from .types import (
    BilbyJobCreationResult,
    BilbyJobSupportingFile,
    JobDetailsInput,
    JobIniInput,
    JobParameterInput,
    JobParameterOutput,
    JobStatusType,
    SupportingFileUploadInput,
    SupportingFileUploadResult,
)
from .utils.derive_job_status import derive_job_status
from .utils.gen_parameter_output import generate_parameter_output
from .utils.jobs.request_file_download_id import request_file_download_ids
from .utils.jobs.request_job_filter import request_job_filter
from .views import (
    create_bilby_job,
    create_bilby_job_from_ini_string,
    create_event_id,
    delete_event_id,
    update_event_id,
    upload_bilby_job,
    upload_external_bilby_job,
    upload_hdf5_bilby_job,
    upload_supporting_files,
)

logger = logging.getLogger(__name__)


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
        fields = "__all__"

    order_by = OrderingFilter(
        fields=(
            ("last_updated", "lastUpdated"),
            ("name", "name"),
        )
    )

    @property
    def qs(self):
        user = self.request.user
        return BilbyJob.user_bilby_job_filter(super().qs, user).prefetch_related("user")


class PublicBilbyJobFilter(FilterSet):
    class Meta:
        model = BilbyJob
        fields = "__all__"

    order_by = OrderingFilter(
        fields=(
            ("last_updated", "last_updated"),
            ("name", "name"),
        )
    )

    @property
    def qs(self):
        user = self.request.user
        return BilbyJob.public_bilby_job_filter(super().qs, user).prefetch_related("user")


class BilbyJobNode(DjangoObjectType):
    class Meta:
        model = BilbyJob
        convert_choices_to_enum = False
        interfaces = (relay.Node,)

    user = graphene.String()
    user_id = graphene.Int()
    job_status = graphene.Field(JobStatusType)
    last_updated = graphene.String()
    params = graphene.Field(JobParameterOutput)
    labels = graphene.List(LabelType)
    event_id = graphene.Field(EventIDType)

    @classmethod
    def get_queryset(parent, queryset, info):
        user = info.context.user
        user_id = user.id if user.is_authenticated else 0

        qs = BilbyJob.bilby_job_filter(queryset, user)
        qs = qs.prefetch_related("user")

        info.context.users = {}

        # Query any job controller information in one go - exclude any job controller ids that are not set
        job_controller_ids = set(qs.exclude(job_controller_id=None).values_list("job_controller_id", flat=True))
        _, jc_jobs = request_job_filter(user_id, ids=list(job_controller_ids))
        info.context.job_controller_jobs = dict(zip([job["id"] for job in jc_jobs], list(jc_jobs), strict=True))

        return qs

    def resolve_user(parent, info):
        try:
            if parent.user:
                return parent.user.name
        except Exception:
            pass
        return "Unknown User"

    def resolve_user_id(parent, info):
        return parent.user_id

    def resolve_last_updated(parent, info):
        return parent.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")

    def resolve_params(parent, info):
        try:
            logger.debug(f"Generating parameters for job {parent.id}")
            return generate_parameter_output(parent)
        except Exception as e:
            logger.error(
                f"Failed to generate parameter output for job {parent.id}: {type(e).__name__}: {e}", exc_info=True
            )
            return None

    def resolve_labels(parent, info):
        return parent.labels.all()

    def resolve_event_id(parent, info):
        return parent.event_id

    def resolve_job_status(parent, info):
        # Uploaded jobs are always complete
        if parent.job_type == BilbyJobType.UPLOADED:
            return {
                "name": JobStatus.display_name(JobStatus.COMPLETED),
                "number": JobStatus.COMPLETED,
                "date": parent.creation_time,
            }

        try:
            status_number, status_name, status_date = derive_job_status(
                info.context.job_controller_jobs.get(parent.job_controller_id)["history"]
            )

            return {
                "name": status_name,
                "number": status_number,
                "date": status_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
        except Exception:
            return {"name": "Unknown", "number": 0, "date": "Unknown"}


class BilbyResultFile(graphene.ObjectType):
    path = graphene.String()
    is_dir = graphene.Boolean()
    file_size = graphene.Decimal()
    download_token = graphene.String()


class BilbyResultFiles(graphene.ObjectType):
    class Input:
        job_id = graphene.ID()

    files = graphene.List(BilbyResultFile)
    job_type = graphene.Int()


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


class Query:
    bilby_job = relay.Node.Field(BilbyJobNode)
    bilby_jobs = DjangoFilterConnectionField(BilbyJobNode, filterset_class=UserBilbyJobFilter)
    public_bilby_jobs = relay.ConnectionField(
        BilbyPublicJobConnection,
        search=graphene.String(),
        time_range=graphene.String(),
        cursor=graphene.Argument(graphene.ID),
        count=graphene.Int(),
    )

    all_labels = relay.ConnectionField(AllLabelsConnection)

    event_id = graphene.Field(EventIDType, event_id=graphene.String(required=True))
    all_event_ids = graphene.List(EventIDType)

    bilby_result_files = graphene.Field(BilbyResultFiles, job_id=graphene.ID(required=True))

    generate_bilby_job_upload_token = graphene.Field(GenerateBilbyJobUploadToken)

    @login_required
    def resolve_generate_bilby_job_upload_token(self, info, **kwargs):
        user = info.context.user
        logger.info(f"User {user.id} requesting job upload token")

        # Create a job upload token
        token = BilbyJobUploadToken.create(user)

        logger.info(f"Generated upload token for user {user.id}")
        # Return the generated token
        return GenerateBilbyJobUploadToken(token=str(token.token))

    def resolve_all_labels(self, info, **kwargs):
        return list_labels()

    def resolve_event_id(self, info, event_id):
        return get_event_id(event_id, info.context.user)

    def resolve_all_event_ids(self, info, **kwargs):
        return list_event_ids_for_user(info.context.user)

    def resolve_public_bilby_jobs(self, info, **kwargs):
        user = info.context.user
        user_id = user.id if user.is_authenticated else 0
        search_term = kwargs.get("search", "*")
        logger.info(
            f"User {user_id} searching public jobs: search='{search_term}', time_range={kwargs.get('time_range')}"
        )

        # Parse the cursor if it was provided and set the first offset to be used by the database search
        # Sometimes the relay resolver fills out all kwarg parameters, but sometimes
        # it doesn't, most likely becuase it hates happiness and all that is good
        # This ensures that "after" is either an int (from a b64 string) or None
        if kwargs.get("after") is None:
            kwargs["after"] = None
        else:
            kwargs["after"] = int(from_global_id(kwargs["after"])[1])

        page_size = kwargs["first"]
        offset = kwargs.get("after") or 0

        public_jobs = list_public_jobs(
            user,
            search=kwargs.get("search", "") or "",
            time_range=kwargs["time_range"],
            page_size=page_size,
            offset=offset,
        )

        records = public_jobs["records"]
        if not records:
            return []

        job_controller_jobs = public_jobs["job_controller_jobs"]

        # Parse the result into graphql objects
        result = []

        for record in records:
            job = record["_source"]
            bilby_job = get_job(record["_id"], user)

            job_node = BilbyPublicJobNode(
                user=job["user"]["name"],
                name=job["job"]["name"],
                description=job["job"]["description"],
                event_id=EventIDType.get_node(info, id=bilby_job.event_id.id) if bilby_job.event_id else None,
                id=to_global_id("BilbyJobNode", bilby_job.id),
            )

            if bilby_job.job_type == BilbyJobType.NORMAL:
                # If there is no job controller record for this job, then the job is broken.
                if bilby_job.id not in job_controller_jobs:
                    job_node.job_status = JobStatusType(name="Unknown", number=0, date=bilby_job.creation_time)
                    job_node.labels = bilby_job.labels.all()
                    job_node.timestamp = bilby_job.creation_time
                else:
                    job_controller_job = job_controller_jobs[bilby_job.id]
                    job_node.job_status = JobStatusType(
                        name=JobStatus.display_name(job_controller_job["history"][0]["state"]),
                        number=job_controller_job["history"][0]["state"],
                        date=job_controller_job["history"][0]["timestamp"],
                    )
                    job_node.labels = bilby_job.labels.all()
                    job_node.timestamp = job_controller_job["history"][0]["timestamp"]

            elif bilby_job.job_type in [BilbyJobType.UPLOADED, BilbyJobType.EXTERNAL]:
                job_node.job_status = JobStatusType(
                    name=JobStatus.display_name(JobStatus.COMPLETED),
                    number=JobStatus.COMPLETED,
                    date=bilby_job.creation_time,
                )
                job_node.labels = bilby_job.labels.all()
                job_node.timestamp = bilby_job.creation_time

            else:
                raise RuntimeError(f"Unknown Bilby Job Type {bilby_job.job_type}")

            result.append(job_node)

        # Nb. The elastic search function requests one extra record than kwargs['first'].
        # This triggers the ArrayConnection used by returning the result array to correctly set
        # hasNextPage correctly, such that infinite scroll works as expected.

        # graphene_django's arrayconnection implementation is a bit crazy. It expects this function to return a full
        # array that has *all* the elements in it, that is then sliced into the expected result. Since the database
        # only returns us what we expect, what we're doing here is reconstructing that array with the requested offset
        # worth of empty elements at the start. We then tac on our records from the database, and the arrayconnection
        # internally slices the correct values from the array and returns that to the client.

        # Furthermore, arrayconnections with offset 0 or 1 are functionally the same, this is why we add a +1 to the
        # value from after if it is provided, otherwise we use 0 (-1 + 1) if no after value is provided.

        after_value = int((kwargs.get("after") or -1) + 1)
        # If it is zero (due to being passed as b64 with a value of zero)
        # This is different to if it is zero due to being None
        if kwargs.get("after") == 0:
            after_value = 1
        real_result = [None] * after_value
        real_result.extend(result)

        return real_result

    @login_required
    def resolve_gwclouduser(self, info, **kwargs):
        return info.context.user

    def resolve_bilby_result_files(self, info, **kwargs):
        # Get the model id of the bilby job
        _, job_id = from_global_id(kwargs.get("job_id"))
        user_id = info.context.user.id if info.context.user.is_authenticated else 0
        logger.info(f"User {user_id} requesting result files for job {job_id}")

        # Try to look up the job with the id provided
        job = get_job(job_id, info.context.user)

        if job.job_type == BilbyJobType.EXTERNAL:
            # There is nothing special we have to do here. The frontend or API will handle the job_type.
            result = [BilbyResultFile(path=ExternalBilbyJob.objects.get(job=job).url)]
        else:
            # Fetch the file list from the job controller
            success, files = job.get_file_list()
            if not success:
                logger.error(f"Failed to get file list for job {job_id}: {files!s}")
                raise Exception("Error getting file list. " + str(files))

            # Generate download tokens for the list of files
            paths = [f["path"] for f in filter(lambda x: not x["isDir"], files)]
            tokens = FileDownloadToken.create(job, paths)

            # Generate a dict that can be used to query the generated tokens
            token_dict = {tk.path: tk.token for tk in tokens}

            # Build the resulting file list and send it back to the client
            result = [
                BilbyResultFile(
                    path=f["path"],
                    is_dir=f["isDir"],
                    file_size=Decimal(f["fileSize"]),
                    download_token=token_dict.get(f["path"], None),
                )
                for f in files
            ]

        return BilbyResultFiles(files=result, job_type=job.job_type)


class EventIDMutation(relay.ClientIDMutation):
    class Input:
        event_id = graphene.String(required=True)
        gps_time = graphene.Decimal(required=True)
        trigger_id = graphene.String()
        nickname = graphene.String()
        is_ligo_event = graphene.Boolean()

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        if user.id not in settings.PERMITTED_EVENT_CREATION_USER_IDS:
            raise Exception("User is not permitted to create EventIDs")

        message = create_event_id(user, **kwargs)

        return EventIDMutation(result=message)


class UpdateEventIDMutation(relay.ClientIDMutation):
    class Input:
        event_id = graphene.String(required=True)
        gps_time = graphene.Float()
        trigger_id = graphene.String()
        nickname = graphene.String()
        is_ligo_event = graphene.Boolean()

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **kwargs):
        user = info.context.user

        if user.id not in settings.PERMITTED_EVENT_CREATION_USER_IDS:
            raise Exception("User is not permitted to modify EventIDs")

        message = update_event_id(user, **kwargs)

        return UpdateEventIDMutation(result=message)


class DeleteEventIDMutation(relay.ClientIDMutation):
    class Input:
        event_id = graphene.String(required=True)

    result = graphene.String()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, event_id):
        user = info.context.user

        if user.id not in settings.PERMITTED_EVENT_CREATION_USER_IDS:
            raise Exception("User is not permitted to delete EventIDs")

        message = delete_event_id(user, event_id)

        return DeleteEventIDMutation(result=message)


class BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        params = JobParameterInput()

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, params):
        user = info.context.user
        logger.info(f"User {user.id} creating new Bilby job: {params.get('details', {}).get('name', 'unnamed')}")

        # Create the bilby job
        bilby_job = create_bilby_job(user, params)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        logger.info(f"Successfully created Bilby job {bilby_job.id} for user {user.id}")
        # Return the bilby job id to the client
        return BilbyJobMutation(result=BilbyJobCreationResult(job_id=job_id))


class BilbyJobFromIniStringMutation(relay.ClientIDMutation):
    class Input:
        params = JobIniInput()

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, params):
        user = info.context.user
        logger.info(f"User {user.id} creating Bilby job from INI string")

        # Create the bilby job
        bilby_job, supporting_file_details = create_bilby_job_from_ini_string(user, params)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        files = [BilbyJobSupportingFile(file_path=f["file_path"], token=f["token"]) for f in supporting_file_details]

        # Return the bilby job id to the client
        return BilbyJobFromIniStringMutation(result=BilbyJobCreationResult(job_id=job_id, supporting_files=files))


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
        job_model_id = from_global_id(job_id)[1]
        logger.info(f"User {user.id} updating job {job_model_id}: {list(kwargs.keys())}")

        # Update privacy of bilby job
        message = update_job(job_model_id, user, **kwargs)[1]

        logger.info(f"Successfully updated job {job_model_id} for user {user.id}")
        # Return the bilby job id to the client
        return UpdateBilbyJobMutation(result=message, job_id=job_id)


class GenerateFileDownloadIds(relay.ClientIDMutation):
    class Input:
        job_id = graphene.ID(required=True)
        download_tokens = graphene.List(graphene.String, required=True)

    result = graphene.List(graphene.String)

    @classmethod
    def mutate_and_get_payload(cls, root, info, job_id, download_tokens):
        user = info.context.user
        user_id = user.id if user.is_authenticated else 0
        job_model_id = from_global_id(job_id)[1]
        logger.info(f"User {user_id} requesting file download IDs for job {job_model_id}: {len(download_tokens)} files")

        # Get the job these file downloads are for
        job = get_job(job_model_id, user)

        # Verify the download tokens and get the paths
        paths = FileDownloadToken.get_paths(job, download_tokens)

        # Check that all tokens were found
        if None in paths:
            logger.warning(f"User {user_id} provided invalid/expired tokens for job {job_model_id}")
            raise GraphQLError("At least one token was invalid or expired.")

        # For uploaded jobs, we can just return the exact some download tokens - this function is basically a no-op
        # for uploaded jobs
        if job.job_type == BilbyJobType.UPLOADED:
            return GenerateFileDownloadIds(result=download_tokens)

        # Request the list of file download ids from the list of paths
        # Only the original job author may generate a file download id
        success, result = request_file_download_ids(job, paths)

        # Report the error if there is one
        if not success:
            raise GraphQLError(result)

        # Return the list of file download ids
        return GenerateFileDownloadIds(result=result)


class UploadBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        upload_token = graphene.String()
        details = JobDetailsInput()
        job_file = Upload(required=True)

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, upload_token, details, job_file):
        logger.info(f"Upload job mutation initiated with token {upload_token}: {details.get('name', 'unnamed')}")

        # Get the token being used to perform the upload - this will return None if the token doesn't exist or
        # is expired
        token = BilbyJobUploadToken.get_by_token(upload_token)
        if not token:
            raise GraphQLError("Job upload token is invalid or expired.")

        # Try uploading the bilby job
        bilby_job = upload_bilby_job(info.context.user, token, details, job_file)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobMutation(result=BilbyJobCreationResult(job_id=job_id))


class UploadSupportingFilesMutation(relay.ClientIDMutation):
    class Input:
        supporting_files = graphene.List(SupportingFileUploadInput)

    result = graphene.Field(SupportingFileUploadResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, supporting_files):
        file_tokens, uploaded_files = [], []
        for f in supporting_files:
            file_tokens.append(f.file_token)
            uploaded_files.append(f.supporting_file)

        # Get the tokens being used to perform the upload - this will return None if the token doesn't exist or
        # if the bilby job is expired
        tokens = SupportingFile.get_by_upload_tokens(file_tokens)
        if not all(tokens):
            raise GraphQLError("At least one supporting file upload token is invalid or expired.")

        # Try uploading the bilby job supporting file
        success = upload_supporting_files(tokens, uploaded_files)

        # Return the success state job id to the client
        return UploadSupportingFilesMutation(result=SupportingFileUploadResult(result=success))


class UploadExternalBilbyJobMutation(relay.ClientIDMutation):
    class Input:
        details = JobDetailsInput()
        ini_file = graphene.String(required=True)
        result_url = graphene.String(required=True)

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, details, ini_file, result_url):
        user = info.context.user
        logger.info(f"User {user.id} uploading external Bilby job: {details.get('name', 'unnamed')} from {result_url}")

        # Try uploading the external bilby job
        bilby_job = upload_external_bilby_job(user, details, ini_file, result_url)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        logger.info(f"Successfully uploaded external job {bilby_job.id} for user {user.id}")
        # Return the bilby job id to the client
        return BilbyJobMutation(result=BilbyJobCreationResult(job_id=job_id))


class UploadHdf5BilbyJobMutation(relay.ClientIDMutation):
    class Input:
        upload_token = graphene.String()
        details = JobDetailsInput()
        hdf5_file = Upload(required=True)
        ini_file = Upload(required=True)

    result = graphene.Field(BilbyJobCreationResult)

    @classmethod
    def mutate_and_get_payload(cls, root, info, upload_token, details, hdf5_file, ini_file):
        logger.info(f"Upload HDF5 job mutation initiated with token {upload_token}: {details.get('name', 'unnamed')}")

        # Get the token being used to perform the upload - this will return None if the token doesn't exist or
        # is expired
        token = BilbyJobUploadToken.get_by_token(upload_token)
        if not token:
            logger.warning(f"Invalid or expired upload token for HDF5 job: {upload_token}")
            raise GraphQLError("Job upload token is invalid or expired.")

        # Try uploading the bilby job with HDF5 file
        bilby_job = upload_hdf5_bilby_job(info.context.user, token, details, hdf5_file, ini_file)

        # Convert the bilby job id to a global id
        job_id = to_global_id("BilbyJobNode", bilby_job.id)

        # Return the bilby job id to the client
        return BilbyJobMutation(result=BilbyJobCreationResult(job_id=job_id))


class Mutation(graphene.ObjectType):
    new_bilby_job = BilbyJobMutation.Field()
    new_bilby_job_from_ini_string = BilbyJobFromIniStringMutation.Field()
    update_bilby_job = UpdateBilbyJobMutation.Field()
    generate_file_download_ids = GenerateFileDownloadIds.Field()
    upload_bilby_job = UploadBilbyJobMutation.Field()
    create_event_id = EventIDMutation.Field()
    update_event_id = UpdateEventIDMutation.Field()
    delete_event_id = DeleteEventIDMutation.Field()
    upload_supporting_files = UploadSupportingFilesMutation.Field()
    upload_external_bilby_job = UploadExternalBilbyJobMutation.Field()
    upload_hdf5_bilby_job = UploadHdf5BilbyJobMutation.Field()
