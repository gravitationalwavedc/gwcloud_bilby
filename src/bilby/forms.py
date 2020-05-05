from django import forms
from .validators import validate_float_string, validate_boolean_string

class BilbyJobForm(forms.Form):
    # Start
    job_name = forms.CharField()
    job_description = forms.CharField()

    # Data
    data_type = forms.CharField()
    hanford = forms.BooleanField(required=False)
    livingston = forms.BooleanField(required=False)
    virgo = forms.BooleanField(required=False)
    signal_duration = forms.FloatField()
    sampling_frequency = forms.FloatField()
    trigger_time = forms.FloatField()
    hanford_minimum_frequency = forms.FloatField()
    hanford_maximum_frequency = forms.FloatField()
    hanford_channel: forms.CharField()
    livingston_minimum_frequency = forms.FloatField()
    livingston_maximum_frequency = forms.FloatField()
    livingston_channel: forms.CharField()
    virgo_minimum_frequency = forms.FloatField()
    virgo_maximum_frequency = forms.FloatField()
    virgo_channel: forms.CharField()

    # Signal
    signal_type = forms.CharField()
    signal_model = forms.CharField()
    mass1 = forms.FloatField()
    mass2 = forms.FloatField()
    luminosity_distance = forms.FloatField()
    psi = forms.FloatField()
    iota = forms.FloatField()
    phase = forms.FloatField()
    merger_time = forms.FloatField()
    ra = forms.FloatField()
    dec = forms.FloatField()

    # Priors
    # mass1: {type: 'fixed', value: '', min: '', max: ''},
    # mass2: {type: 'fixed', value: '', min: '', max: ''},
    # luminosityDistance: {type: 'fixed', value: '', min: '', max: ''},
    # iota: {type: 'fixed', value: '', min: '', max: ''},
    # psi: {type: 'fixed', value: '', min: '', max: ''},
    # phase: {type: 'fixed', value: '', min: '', max: ''},
    # mergerTime: {type: 'fixed', value: '', min: '', max: ''},
    # ra: {type: 'fixed', value: '', min: '', max: ''},
    # dec: {type: 'fixed', value: '', min: '', max: ''}

    # Sampler
    sampler = forms.CharField()
    number = forms.FloatField()