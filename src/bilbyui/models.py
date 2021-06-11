import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from bilbyui.utils.jobs.request_file_list import request_file_list
from bilbyui.utils.jobs.request_job_status import request_job_status
from .utils.parse_ini_file import parse_ini_file


class Label(models.Model):
    name = models.CharField(max_length=50, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    # Protected indicates that the label can not be set by a normal user. Down the track we'll use this flag to
    # determine if only a user with a specific permission may apply this tag to a job
    protected = models.BooleanField(default=False)

    def __str__(self):
        return f"Label: {self.name}"

    @classmethod
    def all(cls):
        """
        Retrieves all labels

        :return: QuerySet of all Labels
        """
        return cls.objects.all()

    @classmethod
    def filter_by_name(cls, labels, include_protected=False):
        """
        Filter all Labels by name in the provided labels

        :param labels: A list of strings representing the label names to match
        :param include_protected: If protected labels should be included
        :return: QuerySet of filtered Labels
        """
        return cls.objects.filter(name__in=labels, protected__in=[False, include_protected])


class BilbyJob(models.Model):
    user_id = models.IntegerField()
    name = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    creation_time = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now_add=True)

    private = models.BooleanField(default=False)

    # The job ini string *should* be the full ini file for the job minus any client specific parameters
    ini_string = models.TextField(blank=True, null=True)

    # The job controller id is the id given by the job controller at submission
    job_controller_id = models.IntegerField(default=None, blank=True, null=True)

    labels = models.ManyToManyField(Label)
    # is_ligo_job indicates if the job has been run using proprietary data. If running a real job with GWOSC, this will
    # be set to False, otherwise a real data job using channels other than GWOSC will result in this value being True
    is_ligo_job = models.BooleanField(default=False)

    class Meta:
        unique_together = (
            ('user_id', 'name'),
        )

    def __str__(self):
        return f"Bilby Job: {self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Whenever a job is saved, we need to regenerate the ini k/v pairs
        parse_ini_file(self)

    @property
    def job_status(self):
        return request_job_status(self)

    def get_file_list(self, path='', recursive=True):
        return request_file_list(self, path, recursive)

    def as_json(self):
        return dict(
            name=self.name,
            description=self.description,
            ini_string=self.ini_string
        )

    @classmethod
    def get_by_id(cls, bid, user):
        """
        Get BilbyJob by the provided id

        This function will raise an exception if:-
        * the job requested is a ligo job, but the user is not a ligo user
        * the job requested is private an not owned by the requesting user

        :param bid: The id of the BilbyJob to return
        :param user: The GWCloudUser instance making the request
        :return: BilbyJob
        """
        job = cls.objects.get(id=bid)

        # Ligo jobs may only be accessed by ligo users
        if job.is_ligo_job and not user.is_ligo:
            raise Exception("Permission Denied")

        # Users can only access the job if it is public or the user owns the job
        if job.private and user.user_id != job.user_id:
            raise Exception("Permission Denied")

        return job

    @classmethod
    def user_bilby_job_filter(cls, qs, user_job_filter):
        """
        Used by UserBilbyJobFilter to filter only jobs owned by the requesting user

        :param qs: The UserBilbyJobFilter queryset
        :param user_job_filter: The UserBilbyJobFilter instance
        :return: The queryset filtered by the requesting user
        """
        return qs.filter(user_id=user_job_filter.request.user.user_id)

    @classmethod
    def public_bilby_job_filter(cls, qs, public_job_filter):
        """
        Used by PublicBilbyJobFilter to filter only public jobs

        :param qs: The PublicBilbyJobFilter queryset
        :param public_job_filter: The PublicBilbyJobFilter instance
        :return: The queryset filtered by public jobs only
        """
        return qs.filter(private=False)

    @classmethod
    def bilby_job_filter(cls, queryset, info):
        """
        Used by BilbyJobNode to filter which jobs are visible to the requesting user.

        A user must be logged in to view any bilby jobs
        A user who is not a ligo user can not view ligo jobs

        :param queryset: The BilbyJobNode queryset
        :param info: The BilbyJobNode queryset info object
        :return: queryset filtered by ligo jobs if required
        """
        if info.context.user.is_anonymous:
            raise Exception("You must be logged in to perform this action.")

        # Users may not view ligo jobs if they are not a ligo user
        if info.context.user.is_ligo:
            return queryset
        else:
            return queryset.exclude(is_ligo_job=True)


class IniKeyValue(models.Model):
    # The job this ini record is for
    job = models.ForeignKey(BilbyJob, on_delete=models.CASCADE, db_index=True)
    # The ini key
    key = models.TextField(db_index=True)
    # The ini value - this is stored as a json dumped value to keep the original type information for the field
    # Generally this will be bool, int/float, str - get the value/type back by using json.loads
    value = models.TextField(db_index=True)
    # The index from the ini file this k/v was generated from (allows forward engineering the ini file from these k/v's)
    index = models.IntegerField()


class FileDownloadToken(models.Model):
    """
    This model tracks files from job file lists which can be used to generate file download tokens from the job
    controller
    """
    # The job this token is for
    job = models.ForeignKey(BilbyJob, on_delete=models.CASCADE, db_index=True)
    # The token sent to the client and used by the client to generate a file download token
    token = models.UUIDField(unique=True, default=uuid.uuid4, db_index=True)
    # The file path this token is for
    path = models.TextField()
    # When the token was created
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    @classmethod
    def create(cls, job, paths):
        """
        Creates a bulk number of FileDownloadToken objects for a specific job and list of paths, and returns the
        created objects
        """
        data = [
            cls(
                job=job,
                path=p
            ) for p in paths
        ]

        return cls.objects.bulk_create(data)

    @classmethod
    def prune(cls):
        """
        Removes any expired tokens from the database
        """
        cls.objects.filter(
            created__lt=timezone.now() - datetime.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY)
        ).delete()

    @classmethod
    def get_paths(cls, job, tokens):
        """
        Returns a list of paths from a list of tokens, any token that isn't found will have a path of None

        The resulting list, will have identical size and ordering to the provided list of tokens
        """
        # First prune any old tokens which may have expired
        cls.prune()

        # Get all objects matching the list of tokens
        objects = {
            str(rec.token): rec.path for rec in cls.objects.filter(job=job, token__in=tokens)
        }

        # Generate the list and return
        return [
            objects[str(tok)] if str(tok) in objects else None for tok in tokens
        ]
