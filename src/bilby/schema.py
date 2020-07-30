import datetime

import graphene
from graphene import relay
from graphene_django.types import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django_filters import FilterSet, OrderingFilter

from .models import BilbyJob, Data, Signal, Prior, Sampler, Label
from .status import JobStatus

from .utils.auth.filter_users import request_filter_users
from .utils.auth.lookup_users import request_lookup_users
from .utils.derive_job_status import derive_job_status
from .utils.jobs.request_job_filter import request_job_filter
from .views import create_bilby_job, update_bilby_job
from .types import OutputStartType, AbstractDataType, AbstractSignalType, AbstractSamplerType, JobStatusType

from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id, to_global_id


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
        return queryset

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
    job_status = graphene.String()
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
        order_by=graphene.String(),
        search=graphene.String(),
        time_range=graphene.String()
    )

    all_labels = graphene.List(LabelType)

    bilby_result_files = graphene.Field(BilbyResultFiles, job_id=graphene.ID(required=True))

    gwclouduser = graphene.Field(UserDetails)

    def resolve_all_labels(self, info, **kwargs):
        return Label.objects.all()

    @login_required
    def resolve_public_bilby_jobs(self, info, **kwargs):
        # Get the search criteria
        search = kwargs.get("search", "")

        # Get the list of search terms
        search_terms = []
        for term in search.split(' '):
            # Remove any extranious whitespace
            term = term.strip().lower()

            # If the term is valid, add it to the list of search terms
            if len(term):
                search_terms.append(term)

        # If there are search terms
        if len(search_terms):
            # First look up a list of users
            _, terms = request_filter_users(" ".join(search_terms), info.context.user.user_id)

            # Collate the user id's to search for jobs on
            user_ids = []
            for term in terms:
                for user in term['users']:
                    user_ids.append(user['userId'])

            jobs = BilbyJob.objects.filter(user_id__in=user_ids)
        else:
            jobs = BilbyJob.objects.all()

        # Make sure every job has a valid job id and is public
        jobs = jobs.filter(job_id__isnull=False, private=False)
        # Calculate the end time for jobs
        time_range = kwargs.get("time_range", "1d")
        end_time = datetime.datetime.now()
        if time_range == "1d":
            end_time -= datetime.timedelta(days=1)
        elif time_range == "1w":
            end_time -= datetime.timedelta(weeks=1)
        elif time_range == "1m":
            end_time -= datetime.timedelta(days=31)
        elif time_range == "1y":
            end_time -= datetime.timedelta(days=365)
        else:
            end_time = None

        # Get job details from the job controller
        _, jc_jobs = request_job_filter(
            info.context.user.user_id,
            ids=[j['job_id'] for j in jobs.values("job_id").distinct()],
            end_time_gt=end_time
        )

        # Make sure that the result is an array
        jc_jobs = jc_jobs or []

        # Get the user id's that match any of the terms
        user_ids = set([j['user'] for j in jc_jobs])

        # Get the user id's from the list of jobs
        _, user_details = request_lookup_users(user_ids, info.context.user.user_id)

        def user_from_id(user_id):
            for u in user_details:
                if u['userId'] == user_id:
                    return u

            return "Unknown User"

        # Match user and job details to the job controller results
        valid_jobs = []
        for job in jc_jobs:
            try:
                job["user"] = user_from_id(job["user"])
                job["job"] = jobs.get(job_id=job["id"])

                job_status, job_status_str, timestamp = derive_job_status(job["history"])
                job["status"] = job_status_str
                job["status_int"] = job_status
                job["timestamp"] = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                job["labels"] = job["job"].labels.all()

                valid_jobs.append(job)
            except Exception:
                pass

        jc_jobs = valid_jobs

        def user_name_from_id(user_id):
            for u in user_details:
                if u['userId'] == user_id:
                    return f"{u['firstName']} {u['lastName']}"

            return "Unknown User"

        # Now do the search
        matched_jobs = []

        # Iterate over each job
        for job in jc_jobs:
            # Iterate over each term and make sure the term exists in the record
            valid = True

            valid_status = [
                JobStatus.PENDING,
                JobStatus.SUBMITTING,
                JobStatus.SUBMITTED,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.COMPLETED
            ]

            status_valid = True

            if not len(search_terms) and job["status_int"] not in valid_status:
                status_valid = False

            if len(search_terms) and job["status_int"] not in valid_status:
                status_valid = False

            status_valid_terms = []
            if not status_valid:
                # Check if any search terms match the job status
                for term in search_terms:
                    if term in job["status"].lower():
                        status_valid = True
                        status_valid_terms.append(term)
                        break

            for term in search_terms:
                if not valid:
                    break

                # Match username, first name and last name
                if term in job["user"]["username"].lower():
                    continue
                if term in job["user"]["firstName"].lower():
                    continue
                if term in job["user"]["lastName"].lower():
                    continue

                # Match job name
                if term in job["job"].name.lower():
                    continue

                # Match description
                if term in job["job"].description.lower():
                    continue

                if term in status_valid_terms:
                    continue

                valid = False

            if valid and status_valid:
                matched_jobs.append(
                    BilbyPublicJobNode(
                        user=user_name_from_id(job["user"]["userId"]),
                        name=job["job"].name,
                        job_status=job["status"],
                        description=job["job"].description,
                        labels=job["labels"],
                        timestamp=job["timestamp"],
                        id=to_global_id("BilbyJobNode", job["job"].id)
                    )
                )

        return matched_jobs

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
        job_id = create_bilby_job(info.context.user.user_id, start, data, signal, prior, sampler)

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
