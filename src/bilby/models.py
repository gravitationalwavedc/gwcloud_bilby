from django.conf import settings
from django.db import models

from .utils.request_job_status import request_job_status
from .variables import *


class BilbyJob(models.Model):
    user_id = models.IntegerField()
    username = models.CharField(max_length=30)
    name = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    creation_time = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now_add=True)

    public = models.BooleanField(default=False)

    job_id = models.IntegerField(default=None, blank=True, null=True)

    class Meta:
        unique_together = (
            ('username', 'name'),
        )

    def __str__(self):
        return 'Bilby Job: {}'.format(self.name)

    @property
    def job_status(self):
        return request_job_status(self)

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
            "default": self.prior.first().prior
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


class Data(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='data', on_delete=models.CASCADE)

    DATA_CHOICES = [
        SIMULATED,
        OPEN
    ]

    data_choice = models.CharField(max_length=20, choices=DATA_CHOICES, default=SIMULATED[0])

    def __str__(self):
        return 'Data container for {}'.format(self.job.name)

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
        HANFORD,
        LIVINGSTON,
        VIRGO,
        SIGNAL_DURATION,
        SAMPLING_FREQUENCY,
        TRIGGER_TIME,
        HANFORD_MIN_FREQ,
        HANFORD_MAX_FREQ,
        HANFORD_CHANNEL,
        LIVINGSTON_MIN_FREQ,
        LIVINGSTON_MAX_FREQ,
        LIVINGSTON_CHANNEL,
        VIRGO_MIN_FREQ,
        VIRGO_MAX_FREQ,
        VIRGO_CHANNEL
    ]

    name = models.CharField(max_length=20, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.CharField(max_length=1000, blank=True, null=True)

    def __str__(self):
        return 'Data parameter {} for Bilby Job {}'.format(self.name, self.job.name)


class Signal(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='signal', on_delete=models.CASCADE)

    SIGNAL_CHOICES = [
        SKIP,
        BBH,
        BNS
    ]

    signal_choice = models.CharField(max_length=50, choices=SIGNAL_CHOICES, default=SKIP[0])
    signal_model = models.CharField(max_length=50, choices=SIGNAL_CHOICES[1:])


class SignalParameter(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='signal_parameter', on_delete=models.CASCADE)
    signal = models.ForeignKey(Signal, related_name='parameter', on_delete=models.CASCADE)

    PARAMETER_CHOICES = [
        MASS1,
        MASS2,
        LUMINOSITY_DISTANCE,
        IOTA,
        PSI,
        PHASE,
        MERGER,
        RA,
        DEC,
    ]

    name = models.CharField(max_length=20, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.FloatField(blank=True, null=True)


class Prior(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='prior', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, blank=False, null=False)

    # PRIOR_CHOICES = [
    #     FIXED,
    #     UNIFORM,
    # ]

    PRIOR_CHOICES = [
        PRIOR_4S,
        PRIOR_8S,
        PRIOR_16S,
        PRIOR_32S,
        PRIOR_64S,
        PRIOR_128S
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
        DYNESTY,
        NESTLE,
        EMCEE,
    ]

    sampler_choice = models.CharField(max_length=15, choices=SAMPLER_CHOICES, default=DYNESTY[0])

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
    name = models.CharField(max_length=50, blank=False, null=False)
    value = models.CharField(max_length=50, blank=True, null=True)
