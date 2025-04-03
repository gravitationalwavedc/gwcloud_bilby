import datetime
import json
import os
import uuid
from pathlib import Path

import elasticsearch
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from bilbyui.utils.jobs.request_file_list import request_file_list
from .constants import BILBY_JOB_TYPE_CHOICES, BilbyJobType
from .utils.auth.lookup_users import request_lookup_users
from .utils.embargo import embargo_filter
from .utils.jobs.submit_job import submit_job
from .utils.misc import is_ligo_user
from .utils.parse_ini_file import parse_ini_file


class Label(models.Model):
    name = models.CharField(max_length=50, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    # Protected indicates that the label can not be set by a normal user. Down the track we'll use this flag to
    # determine if only a user with a specific permission may apply this tag to a job
    protected = models.BooleanField(default=False)

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

    def __str__(self):
        return f"Label: {self.name}"


@receiver(post_save, sender=Label, dispatch_uid="label_save")
def label_save(sender, instance, **kwargs):
    for job in instance.bilbyjob_set.all():
        job.elastic_search_update()


class EventID(models.Model):
    event_id = models.CharField(
        max_length=15,
        blank=False,
        null=False,
        unique=True,
        validators=[RegexValidator(regex=r"^GW\d{6}_\d{6}$", message="Must be of the form GW123456_123456")],
    )
    trigger_id = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[RegexValidator(regex=r"^S\d{6}[a-z]{1,2}$", message="Must be of the form S123456a")],
    )
    nickname = models.CharField(max_length=20, blank=True, null=True)
    is_ligo_event = models.BooleanField(default=False)
    gps_time = models.FloatField(default=1126259462.391)

    @classmethod
    def get_by_event_id(cls, event_id, user):
        event = cls.objects.get(event_id=event_id)

        if event.is_ligo_event and not is_ligo_user(user):
            raise Exception("Permission Denied")

        return event

    @classmethod
    def filter_by_ligo(cls, is_ligo):
        # Users may not view ligo IDs if they are not a ligo user
        if is_ligo:
            return cls.objects.all()
        else:
            return cls.objects.exclude(is_ligo_event=True)

    @classmethod
    def create(cls, event_id, gps_time, trigger_id=None, nickname=None, is_ligo_event=False):
        event = cls(
            event_id=event_id,
            trigger_id=trigger_id,
            nickname=nickname,
            is_ligo_event=is_ligo_event,
            gps_time=gps_time,
        )
        event.clean_fields()  # Validate IDs
        event.save()
        return event

    def update(self, gps_time=None, trigger_id=None, nickname=None, is_ligo_event=False):
        if gps_time is not None:
            self.gps_time = gps_time
        if trigger_id is not None:
            self.trigger_id = trigger_id
        if nickname is not None:
            self.nickname = nickname
        if is_ligo_event is not None:
            self.is_ligo_event = is_ligo_event
        self.clean_fields()  # Validate IDs
        self.save()

    def __str__(self):
        return f"EventID: {self.event_id}"


@receiver(post_save, sender=EventID, dispatch_uid="event_id_save")
def event_id_save(sender, instance, **kwargs):
    for job in instance.bilbyjob_set.all():
        job.elastic_search_update()


class BilbyJob(models.Model):
    class Meta:
        unique_together = (("user_id", "name"),)

        ordering = ("-last_updated", "name")

    user_id = models.IntegerField()
    name = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    creation_time = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    private = models.BooleanField(default=False)

    # The job ini string *should* be the full ini file for the job minus any client specific parameters
    ini_string = models.TextField()

    # The job controller id is the id given by the job controller at submission
    job_controller_id = models.IntegerField(default=None, blank=True, null=True)

    labels = models.ManyToManyField(Label)
    event_id = models.ForeignKey(EventID, default=None, null=True, on_delete=models.SET_NULL)
    # is_ligo_job indicates if the job has been run using proprietary data. If running a real job with GWOSC, this will
    # be set to False, otherwise a real data job using channels other than GWOSC will result in this value being True
    is_ligo_job = models.BooleanField(default=False)

    # The type of job
    job_type = models.IntegerField(default=BilbyJobType.NORMAL, choices=BILBY_JOB_TYPE_CHOICES)

    # The cluster (as a string) that this job was submitted to. This is mainly used to track the cluster that the job
    # should be uploaded to once the supporting files are uploaded
    cluster = models.TextField(null=True)

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

        # Users can only access the job if it is public or (the user is authenticated AND the user also owns the job)
        if job.private and (user.is_anonymous or user.id != job.user_id):
            raise Exception("Permission Denied")

        return job

    @classmethod
    def user_bilby_job_filter(cls, qs, user):
        """
        Used by UserBilbyJobFilter to filter only jobs owned by the requesting user

        :param qs: The UserBilbyJobFilter queryset
        :param user_job_filter: The UserBilbyJobFilter instance
        :return: The queryset filtered by the requesting user
        """
        if user.is_anonymous:
            raise Exception("Permission Denied")

        return embargo_filter(qs.filter(user_id=user.id), user)

    @classmethod
    def public_bilby_job_filter(cls, qs, user):
        """
        Used by PublicBilbyJobFilter to filter only public jobs

        :param qs: The PublicBilbyJobFilter queryset
        :param public_job_filter: The PublicBilbyJobFilter instance
        :return: The queryset filtered by public jobs only
        """
        return embargo_filter(qs.filter(private=False), user)

    @classmethod
    def bilby_job_filter(cls, qs, user):
        """
        Used by BilbyJobNode to filter which jobs are visible to the requesting user.

        A user who is not logged in can only see public jobs
        A user who is logged in can only see their own jobs + public jobs
        A user who is not a ligo user can not view ligo jobs

        :param qs: The BilbyJobNode qs
        :param info: The BilbyJobNode qs info object
        :return: qs filtered by ligo jobs if required
        """

        if user.is_anonymous:
            # User isn't logged in - only allow public jobs
            return embargo_filter(qs.filter(private=False, is_ligo_job=False), user)

        if not is_ligo_user(user):
            # If the job is not a ligo job and (the job is the current user's job or the job is public)
            return embargo_filter(
                qs.filter(Q(is_ligo_job=False) & (Q(user_id=user.id) | Q(private=False))),
                user,
            )

        # If the job is the current user's job or the job is public
        return embargo_filter(qs.filter(Q(user_id=user.id) | Q(private=False)), user)

    @classmethod
    def prune_supporting_files_jobs(cls):
        """
        This function removes any jobs that have supporting files that have not been uploaded within the time specified
        by UPLOAD_SUPPORTING_FILE_EXPIRY
        """
        removal_time = timezone.now() - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY)

        expired_supporting_file_job_ids = SupportingFile.objects.filter(
            job__creation_time__lt=removal_time, upload_token__isnull=False
        )

        cls.objects.filter(id__in=expired_supporting_file_job_ids).delete()

    def get_upload_directory(self):
        """
        Returns the upload directory of the job - only relevant to uploaded jobs.
        """
        return os.path.join(settings.JOB_UPLOAD_DIR, str(self.id))

    def has_supporting_files(self):
        """
        Checks if this job has any supporting files
        """
        return self.supportingfile_set.exists()

    def submit(self):
        # Create the parameter json
        job_params = self.as_dict()

        # Ask the job controller to submit the job
        result = submit_job(self.user_id, job_params, self.cluster)

        # Save the job id
        self.job_controller_id = result["jobId"]
        self.save()

    def __str__(self):
        return f"Bilby Job: {self.name}"

    def save(self, *args, **kwargs):
        # There must be an ini string
        assert self.ini_string, f"Job {self.id} - {self.name} is missing ini string"

        super().save(*args, **kwargs)

        # Whenever a job is saved, we need to regenerate the ini k/v pairs
        parse_ini_file(self)

        # We also need to update our record in elastic search to keep the mysql database and elastic search database
        # in sync
        self.elastic_search_update()

    def get_file_list(self, path="", recursive=True):
        return request_file_list(self, path, recursive)

    def as_dict(self):
        """
        Converts this job in to a dictionary that can be submitted to the bundle for submission
        """
        # Iterate over any supporting files and generate the supporting file details
        supporting_file_details = []
        for supporting_file in self.supportingfile_set.all():
            supporting_file_details.append(
                {
                    "type": supporting_file.file_type,
                    "key": supporting_file.key,
                    "file_name": supporting_file.file_name,
                    "token": str(supporting_file.download_token),
                }
            )

        return dict(
            name=self.name,
            description=self.description,
            ini_string=self.ini_string,
            supporting_files=supporting_file_details,
        )

    def elastic_search_update(self):
        """
        Updates this bilby job entry in elastic search
        """
        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            return

        es = elasticsearch.Elasticsearch(
            hosts=[settings.ELASTIC_SEARCH_HOST],
            api_key=settings.ELASTIC_SEARCH_API_KEY,
            verify_certs=False,
        )

        # Get the user details for this job
        _, users = request_lookup_users([self.user_id], 0)
        user = users[0]

        # Generate the document for insertion or update in elastic search
        doc = {
            "user": {"name": user["name"]},
            "job": {
                "name": self.name,
                "description": self.description,
                "creationTime": self.creation_time,
                "lastUpdatedTime": self.last_updated,
            },
            "labels": [{"name": label.name, "description": label.description} for label in self.labels.all()],
            "eventId": None,
            "ini": {kv.key: json.loads(kv.value) for kv in self.inikeyvalue_set.filter(processed=False)},
            "params": {kv.key: json.loads(kv.value) for kv in self.inikeyvalue_set.filter(processed=True)},
            "_private_info_": {"userId": self.user_id, "private": self.private},
        }

        # Set the event id if one is set on the job
        if self.event_id:
            doc["eventId"] = {
                "eventId": self.event_id.event_id,
                "triggerId": self.event_id.trigger_id,
                "nickname": self.event_id.nickname,
                "gpsTime": self.event_id.gps_time,
            }

        # First try to update the document in elastic search if it exists, otherwise insert the new document
        try:
            es.update(index=settings.ELASTIC_SEARCH_INDEX, id=self.id, doc=doc)
        except elasticsearch.NotFoundError:
            es.index(index=settings.ELASTIC_SEARCH_INDEX, id=self.id, document=doc)

    def elastic_search_remove(self):
        """
        Deletes the elastic search record for this job
        """
        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            return

        es = elasticsearch.Elasticsearch(
            hosts=[settings.ELASTIC_SEARCH_HOST],
            api_key=settings.ELASTIC_SEARCH_API_KEY,
            verify_certs=False,
        )

        es.delete(index=settings.ELASTIC_SEARCH_INDEX, id=self.id)


def on_bilby_job_label_add_rem(sender, instance, action, pk_set, **kwargs):
    if action in ["post_add", "post_remove"]:
        instance.elastic_search_update()


m2m_changed.connect(on_bilby_job_label_add_rem, sender=BilbyJob.labels.through)


@receiver(pre_delete, sender=BilbyJob, dispatch_uid="bilby_job_delete_signal")
def bilby_job_delete_signal(sender, instance, using, **kwargs):
    instance.elastic_search_remove()


class ExternalBilbyJob(models.Model):
    """
    This model stores information about bilby jobs that have external results. For example a job
    where the data file is stored on Zenodo
    """

    job = models.ForeignKey(BilbyJob, on_delete=models.CASCADE)
    url = models.URLField()


class SupportingFile(models.Model):
    """
    This model stores information about supporting files for bilby jobs. This can include PSD, Calibration, Prior, GPS,
    Time Slide and Injection files. Doesn't include a timestamp, as these records will be created at the same time as a
    BilbyJob is.
    """

    PSD = "psd"
    CALIBRATION = "cal"
    PRIOR = "pri"
    GPS = "gps"
    TIME_SLIDE = "tsl"
    INJECTION = "inj"
    NUMERICAL_RELATIVITY = "nmr"
    DISTANCE_MARGINALIZATION_LOOKUP_TABLE = "dml"
    DATA = "dat"

    job = models.ForeignKey(BilbyJob, on_delete=models.CASCADE, db_index=True)
    # What type of supporting file this is
    file_type = models.CharField(max_length=3)
    # The dictionary key of the supporting file if one is specified (ie, L1, V1 etc). If this is null then the config
    # option is a single file. ie gps-file = <some path>. If the key is set then it's part of a config dictionary
    # ie psd-file = {<key>: <some path>}
    key = models.TextField(null=True)
    # The original file name (WITHOUT A PATH)
    file_name = models.TextField()
    # The file upload token. This token is set to None once the supporting file has been uploaded
    upload_token = models.UUIDField(unique=True, null=True, default=uuid.uuid4, db_index=True)
    # The file download token
    download_token = models.UUIDField(unique=True, default=uuid.uuid4, db_index=True)

    @classmethod
    def save_from_parsed(cls, bilby_job, supporting_files, uploaded=False):
        """
        Takes the output from parse_supporting_files and generates the relevant SupportingFile records

        param bilby_job: The BilbyJob instance that the supporting files belongs to
        param supporting_files: Dictionary of supporting files returned from parse_supporting_files function
        param uploaded: If this is true, the supporting file will be marked as uploaded (No upload token set)
        """
        extra = {}
        if uploaded:
            extra["upload_token"] = None

        bulk_items = []
        result_files = []
        for supporting_file_type, details in supporting_files.items():
            if type(details) is list:
                for element in details:
                    for k, f in element.items():
                        result_files.append({"file_path": f})

                        bulk_items.append(
                            cls(
                                job=bilby_job,
                                file_type=supporting_file_type,
                                key=k,
                                file_name=Path(f).name,
                                **extra,
                            )
                        )

            elif type(details) is str:
                result_files.append({"file_path": details})

                bulk_items.append(
                    cls(
                        job=bilby_job,
                        file_type=supporting_file_type,
                        key=None,
                        file_name=Path(details).name,
                        **extra,
                    )
                )

        created = cls.objects.bulk_create(bulk_items)

        # Map the tokens for the created files to the returned supporting files details
        for i, v in enumerate(created):
            result_files[i]["token"] = created[i].upload_token
            result_files[i]["download_token"] = created[i].download_token

        return result_files

    @classmethod
    def get_by_upload_token(cls, token):
        """
        Retrieves the SupportingFile object matching the provided upload token. Returns None if the token doesn't
        exist or the bilby job's file uploads have expired.
        """
        BilbyJob.prune_supporting_files_jobs()

        inst = cls.objects.filter(upload_token=token)
        if not inst.exists():
            return None

        return inst.first()

    @classmethod
    def get_by_upload_tokens(cls, tokens):
        """
        Retrieves the SupportingFile objects matching the provided upload tokens. Returns None for any
        specific SupportingFile if the token doesn't exist or the bilby job's file uploads have expired.
        """
        return [cls.get_by_upload_token(token) for token in tokens]

    @classmethod
    def get_unuploaded_supporting_files(cls, job):
        """
        Retrieves all supporting files that have not yet been uploaded for the specified job
        """
        return SupportingFile.objects.filter(job=job, upload_token__isnull=False)

    @classmethod
    def get_by_download_token(cls, token):
        """
        Retrieves the SupportingFile object matching the provided download token. Returns None if the token doesn't
        exist or the file is not yet uploaded.
        """
        inst = cls.objects.filter(download_token=token, upload_token__isnull=True)
        if not inst.exists():
            return None

        return inst.first()


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
    # If this key/value pair represents the processed value (ie, it's been parsed through Bilby's Input() class)
    processed = models.BooleanField(default=False)


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
    def get_by_token(cls, token):
        """
        Returns the instance matching the specified token, or None if expired or not found
        """
        # First prune any old tokens which may have expired
        cls.prune()

        # Next try to find the instance matching the specified token
        inst = cls.objects.filter(token=token)
        if not inst.exists():
            return None

        return inst.first()

    @classmethod
    def create(cls, job, paths):
        """
        Creates a bulk number of FileDownloadToken objects for a specific job and list of paths, and returns the
        created objects
        """
        data = [cls(job=job, path=p) for p in paths]

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
        objects = {str(rec.token): rec.path for rec in cls.objects.filter(job=job, token__in=tokens)}

        # Generate the list and return
        return [objects[str(tok)] if str(tok) in objects else None for tok in tokens]


class BilbyJobUploadToken(models.Model):
    """
    This model tracks file upload tokens that can be used to upload bilby jobs rather than using traditional JWT
    authentication
    """

    # The job upload token
    token = models.UUIDField(unique=True, default=uuid.uuid4, db_index=True)
    # The ID of the user the upload token was created for (Used to provide the user of the uploaded job)
    user_id = models.IntegerField()
    # If the user creating the upload token was a ligo user or not
    is_ligo = models.BooleanField()
    # When the token was created
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    @classmethod
    def get_by_token(cls, token):
        """
        Returns the instance matching the specified token, or None if expired or not found
        """
        # First prune any old tokens which may have expired
        cls.prune()

        # Next try to find the instance matching the specified token
        inst = cls.objects.filter(token=token)
        if not inst.exists():
            return None

        return inst.first()

    @classmethod
    def create(cls, user):
        """
        Creates a BilbyJobUploadToken object
        """
        # First prune any old tokens which may have expired
        cls.prune()

        # Next create and return a new token instance
        return cls.objects.create(user_id=user.id, is_ligo=is_ligo_user(user))

    @classmethod
    def prune(cls):
        """
        Removes any expired tokens from the database
        """
        cls.objects.filter(
            created__lt=timezone.now() - datetime.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY)
        ).delete()


class AnonymousMetrics(models.Model):
    """
    Used to track information about anonymous users accessing the system for reporting purposes.
    """

    # The public (Persistent) user identifier
    public_id = models.UUIDField()
    # The session identifier
    session_id = models.UUIDField()
    # When the request was made
    timestamp = models.DateTimeField(auto_now_add=True)
    # The graphql query
    request = models.TextField()
    # The graphql parameters if any (as json)
    params = models.TextField()
