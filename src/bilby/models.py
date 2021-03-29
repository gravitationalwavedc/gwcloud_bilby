from django.db import models

from bilby.utils.jobs.request_file_download_id import request_file_download_id
from bilby.utils.jobs.request_file_list import request_file_list
from bilby.utils.jobs.request_job_status import request_job_status
from .variables import bilby_parameters


class Label(models.Model):
    name = models.CharField(max_length=50, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

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
    def filter_by_name(cls, labels):
        """
        Filter all Labels by name in the provided labels

        :param labels: A list of strings representing the label names to match
        :return: QuerySet of filtered Labels
        """
        return cls.objects.filter(name__in=labels)


class BilbyJob(models.Model):
    user_id = models.IntegerField()
    name = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    creation_time = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now_add=True)

    private = models.BooleanField(default=False)

    job_id = models.IntegerField(default=None, blank=True, null=True)

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

    @property
    def job_status(self):
        return request_job_status(self)

    def get_file_list(self, path='', recursive=True):
        return request_file_list(self, path, recursive)

    def get_file_download_id(self, path):
        return request_file_download_id(self, path)

    def as_json(self):
        # Get the data container type for this job
        data = {
            "type": self.data.data_choice
        }

        # Iterate over the data parameters
        for d in self.data_parameter.all():
            data[d.name] = d.value

        # Get the signal data
        signal = {
            'model': self.signal.signal_model
        }
        for s in self.signal_parameter.all():
            signal[s.name] = s.value

        # Get the prior data
        prior = {
            "default": self.prior.prior_choice
        }

        # for p in self.prior.all():
        # if p.prior_choice in FIXED:
        #     prior[p.name] = {
        #         "type": "fixed",
        #         "value": p.fixed_value
        #     }
        # elif p.prior_choice in UNIFORM:
        #     prior[p.name] = {
        #         "type": "uniform",
        #         "min": p.uniform_min_value,
        #         "max": p.uniform_max_value
        #     }

        # Get the sampler type
        sampler = {
            "type": self.sampler.sampler_choice
        }

        # Iterate over the sampler parameters
        for s in self.sampler_parameter.all():
            sampler[s.name] = s.value

        return dict(
            name=self.name,
            description=self.description,
            data=data,
            signal=signal,
            priors=prior,
            sampler=sampler
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


class Data(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='data', on_delete=models.CASCADE)

    DATA_CHOICES = [
        bilby_parameters.SIMULATED,
        bilby_parameters.REAL
    ]

    data_choice = models.CharField(max_length=20, choices=DATA_CHOICES, default=bilby_parameters.SIMULATED[0])

    def __str__(self):
        return f"Data container for {self.job.name}"

    def as_json(self):
        return dict(
            id=self.id,
            value=dict(
                job=self.job.id,
                choice=self.data_choice,
            ),
        )


class DataParameter(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='data_parameter', on_delete=models.CASCADE)
    data = models.ForeignKey(Data, related_name='parameter', on_delete=models.CASCADE)

    PARAMETER_CHOICES = [
        bilby_parameters.HANFORD,
        bilby_parameters.LIVINGSTON,
        bilby_parameters.VIRGO,
        bilby_parameters.SIGNAL_DURATION,
        bilby_parameters.SAMPLING_FREQUENCY,
        bilby_parameters.TRIGGER_TIME,
        bilby_parameters.HANFORD_MIN_FREQ,
        bilby_parameters.HANFORD_MAX_FREQ,
        bilby_parameters.HANFORD_CHANNEL,
        bilby_parameters.LIVINGSTON_MIN_FREQ,
        bilby_parameters.LIVINGSTON_MAX_FREQ,
        bilby_parameters.LIVINGSTON_CHANNEL,
        bilby_parameters.VIRGO_MIN_FREQ,
        bilby_parameters.VIRGO_MAX_FREQ,
        bilby_parameters.VIRGO_CHANNEL
    ]

    name = models.CharField(max_length=50, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.CharField(max_length=1000, blank=True, null=True)

    def __str__(self):
        return f"Data parameter {self.name} for Bilby Job {self.job.name}"


class Signal(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='signal', on_delete=models.CASCADE)

    SIGNAL_CHOICES = [
        bilby_parameters.SKIP,
        bilby_parameters.BBH,
        bilby_parameters.BNS
    ]

    signal_choice = models.CharField(max_length=50, choices=SIGNAL_CHOICES, default=bilby_parameters.SKIP[0])
    signal_model = models.CharField(max_length=50, choices=SIGNAL_CHOICES[1:])


class SignalParameter(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='signal_parameter', on_delete=models.CASCADE)
    signal = models.ForeignKey(Signal, related_name='parameter', on_delete=models.CASCADE)

    PARAMETER_CHOICES = [
        bilby_parameters.MASS1,
        bilby_parameters.MASS2,
        bilby_parameters.LUMINOSITY_DISTANCE,
        bilby_parameters.IOTA,
        bilby_parameters.PSI,
        bilby_parameters.PHASE,
        bilby_parameters.MERGER,
        bilby_parameters.RA,
        bilby_parameters.DEC,
    ]

    name = models.CharField(max_length=50, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.FloatField(blank=True, null=True)


class Prior(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='prior', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, blank=False, null=False)

    # PRIOR_CHOICES = [
    #     FIXED,
    #     UNIFORM,
    # ]

    PRIOR_CHOICES = [
        bilby_parameters.PRIOR_4S,
        bilby_parameters.PRIOR_8S,
        bilby_parameters.PRIOR_16S,
        bilby_parameters.PRIOR_32S,
        bilby_parameters.PRIOR_64S,
        bilby_parameters.PRIOR_128S
    ]

    # prior_choice = models.CharField(max_length=20, choices=PRIOR_CHOICES, default=FIXED[0])
    # fixed_value = models.FloatField(blank=True, null=True)
    # uniform_min_value = models.FloatField(blank=True, null=True)
    # uniform_max_value = models.FloatField(blank=True, null=True)

    prior_choice = models.CharField(max_length=4, choices=PRIOR_CHOICES)

    class Meta:
        unique_together = (
            ('job', 'name')
        )


class Sampler(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='sampler', on_delete=models.CASCADE)

    SAMPLER_CHOICES = [
        bilby_parameters.DYNESTY,
        bilby_parameters.NESTLE,
        bilby_parameters.EMCEE,
    ]

    sampler_choice = models.CharField(max_length=15, choices=SAMPLER_CHOICES, default=bilby_parameters.DYNESTY[0])

    def as_json(self):
        return dict(
            id=self.id,
            value=dict(
                job=self.job.id,
                choice=self.sampler_choice,
            ),
        )


class SamplerParameter(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='sampler_parameter', on_delete=models.CASCADE)
    sampler = models.ForeignKey(Sampler, related_name='parameter', on_delete=models.CASCADE)

    PARAMETER_CHOICES = [
        bilby_parameters.NLIVE,
        bilby_parameters.NACT,
        bilby_parameters.MAXMCMC,
        bilby_parameters.WALKS,
        bilby_parameters.DLOGZ,
        bilby_parameters.CPUS
    ]

    name = models.CharField(max_length=50, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.FloatField(blank=True, null=True)
