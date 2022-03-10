import datetime
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from bilbyui.utils.jobs.request_file_list import request_file_list
from bilbyui.utils.jobs.request_job_status import request_job_status
from .utils.jobs.submit_job import submit_job
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


class EventID(models.Model):
    event_id = models.CharField(
        max_length=15,
        blank=False,
        null=False,
        unique=True,
        validators=[RegexValidator(regex=r'^GW\d{6}_\d{6}$', message='Must be of the form GW123456_123456')]
    )
    trigger_id = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[RegexValidator(regex=r'^S\d{6}[a-z]{1,2}$', message='Must be of the form S123456a')]
    )
    nickname = models.CharField(max_length=20, blank=True, null=True)
    is_ligo_event = models.BooleanField(default=False)

    @classmethod
    def get_by_event_id(cls, event_id, user):
        event = cls.objects.get(event_id=event_id)

        if event.is_ligo_event and not user.is_ligo:
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
    def create(cls, event_id, trigger_id=None, nickname=None, is_ligo_event=False):
        event = cls(
            event_id=event_id,
            trigger_id=trigger_id,
            nickname=nickname,
            is_ligo_event=is_ligo_event
        )
        event.clean_fields()  # Validate IDs
        event.save()
        return event

    def update(self, trigger_id=None, nickname=None, is_ligo_event=False):
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


class BilbyJob(models.Model):
    class Meta:
        unique_together = (
            ('user_id', 'name'),
        )

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
    event_id = models.ForeignKey(EventID, default=None, null=True, on_delete=models.SET_NULL)
    # is_ligo_job indicates if the job has been run using proprietary data. If running a real job with GWOSC, this will
    # be set to False, otherwise a real data job using channels other than GWOSC will result in this value being True
    is_ligo_job = models.BooleanField(default=False)

    # If the job was an uploaded or naturally run job. If this is true, then the job was created by the job upload
    # mutation, otherwise it was created by either new job or new ini job
    is_uploaded_job = models.BooleanField(default=False)

    # The cluster (as a string) that this job was submitted to. This is mainly used to track the cluster that the job
    # should be uploaded to once the supporting files are uploaded
    cluster = models.TextField(null=True)

    @property
    def job_status(self):
        return request_job_status(self)

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

    @classmethod
    def prune_supporting_files_jobs(cls):
        """
        This function removes any jobs that have supporting files that have not been uploaded within the time specified
        by UPLOAD_SUPPORTING_FILE_EXPIRY
        """
        removal_time = timezone.now() - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY)

        expired_supporting_file_job_ids = SupportingFile.objects.filter(
            job__creation_time__lt=removal_time,
            upload_token__isnull=False
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
        job_params = self.as_json()

        # Ask the job controller to submit the job
        result = submit_job(self.user_id, job_params, self.cluster)

        # Save the job id
        self.job_controller_id = result["jobId"]
        self.save()

    def __str__(self):
        return f"Bilby Job: {self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Whenever a job is saved, we need to regenerate the ini k/v pairs
        parse_ini_file(self)

    def get_file_list(self, path='', recursive=True):
        return request_file_list(self, path, recursive)

    def as_json(self):
        """
        Converts this job in to a json blob that can be submitted to the bundle for submission
        """
        # Iterate over any supporting files and generate the supporting file details
        supporting_file_details = []
        for supporting_file in self.supportingfile_set.all():
            supporting_file_details.append({
                'type': supporting_file.file_type,
                'key': supporting_file.key,
                'file_name': supporting_file.file_name,
                'token': supporting_file.download_token
            })

        return dict(
            name=self.name,
            description=self.description,
            ini_string=self.ini_string,
            supporting_files=supporting_file_details
        )


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
    def save_from_parsed(cls, bilby_job, supporting_files):
        """
        Takes the output from parse_supporting_files and generates the relevant SupportingFile records

        param bilby_job: The BilbyJob instance that the supporting files belongs to
        param supporting_files: Dictionary of supporting files returned from parse_supporting_files function
        """
        bulk_items = []
        result_files = []
        for supporting_file_type, details in supporting_files.items():
            if type(details) is list:
                for element in details:
                    for k, f in element.items():
                        result_files.append({'file_path': f})

                        bulk_items.append(
                            cls(
                                job=bilby_job,
                                file_type=supporting_file_type,
                                key=k,
                                file_name=Path(f).name
                            )
                        )

            elif type(details) is str:
                result_files.append({'file_path': details})

                bulk_items.append(
                    cls(
                        job=bilby_job,
                        file_type=supporting_file_type,
                        key=None,
                        file_name=Path(details).name
                    )
                )

        created = cls.objects.bulk_create(bulk_items)

        # Map the tokens for the created files to the returned supporting files details
        for i, v in enumerate(created):
            result_files[i]['token'] = created[i].upload_token

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
        return cls.objects.create(user_id=user.user_id, is_ligo=user.is_ligo)

    @classmethod
    def prune(cls):
        """
        Removes any expired tokens from the database
        """
        cls.objects.filter(
            created__lt=timezone.now() - datetime.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY)
        ).delete()
