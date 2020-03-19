from django.conf import settings
from django.db import models

from .variables import *


class BilbyJob(models.Model):
    user_id = models.IntegerField()
    username = models.CharField(max_length=30)
    name = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    creation_time = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            ('username', 'name'),
        )

    def __str__(self):
        return 'Bilby Job: {}'.format(self.name)


class Data(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='data', on_delete=models.CASCADE)

    DATA_CHOICES = [
        SIMULATED,
        OPEN
    ]

    data_choice = models.CharField(max_length=20, choices=DATA_CHOICES, default=SIMULATED[0])

    def __str__(self):
        return 'Data container for {}'.format(self.job.name)

class DataParameter(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='data_parameter', on_delete=models.CASCADE)
    data = models.ForeignKey(Data, related_name='parameter', on_delete=models.CASCADE)

    PARAMETER_CHOICES = [
        HANFORD,
        LIVINGSTON,
        VIRGO,
        SIGNAL_DURATION,
        SAMPLING_FREQUENCY,
        START_TIME
    ]

    name = models.CharField(max_length=20, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.CharField(max_length=1000, blank=True, null=True)
    
    def __str__(self):
        return 'Data parameter {} for Bilby Job {}'.format(self.name, self.job.name)

class Signal(models.Model):
    job = models.OneToOneField(BilbyJob, related_name='signal', on_delete=models.CASCADE)

    SIGNAL_CHOICES = [
        SKIP,
        BBH
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
        GEOCENT,
        RA,
        DEC,
    ]

    name = models.CharField(max_length=20, choices=PARAMETER_CHOICES, blank=False, null=False)
    value = models.FloatField(blank=True, null=True)

class Prior(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='job_prior', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, blank=False, null=False)

    PRIOR_CHOICES = [
        FIXED,
        UNIFORM,
    ]

    prior_choice = models.CharField(max_length=20, choices=PRIOR_CHOICES, default=FIXED[0])
    fixed_value = models.FloatField(blank=True, null=True)
    uniform_min_value = models.FloatField(blank=True, null=True)
    uniform_max_value = models.FloatField(blank=True, null=True)

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

class SamplerParameter(models.Model):
    job = models.ForeignKey(BilbyJob, related_name='sampler_parameter', on_delete=models.CASCADE)
    sampler = models.ForeignKey(Sampler, related_name='parameter', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, blank=False, null=False)
    value = models.CharField(max_length=50, blank=True, null=True)