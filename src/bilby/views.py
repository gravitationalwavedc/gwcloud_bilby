from .forms import BilbyJobForm
from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Prior, Sampler, SamplerParameter


def create_bilby_job(user_id, username, start, data, signal, prior, sampler):
    validate_form = BilbyJobForm(data={**start, **data, **signal, **sampler})
    # should be making use of cleaned_data below
    
    bilby_job = BilbyJob(
        user_id = user_id,
        username = username,
        name = start.name,
        description = start.description
    )
    bilby_job.save()

    job_data = Data(job=bilby_job, data_choice=data.data_choice)
    job_data.save()

    for key, val in data.items():
        if key not in ['data_choice']:
            data_param = DataParameter(job=bilby_job, data=job_data, name=key, value=val)
            data_param.save()

    job_signal = Signal(job=bilby_job, signal_choice=signal.signal_choice, signal_model=signal.signal_model)
    job_signal.save()

    for key, val in signal.items():
        if key not in ['signal_choice', 'signal_model']:
            signal_param = SignalParameter(job=bilby_job, signal=job_signal, name=key, value=val)
            signal_param.save()

    for key, val in prior.items():
        job_prior = Prior(job=bilby_job, name=key, prior_choice=val.type)
        if val.type == 'fixed':
            job_prior.fixed_value = val.value
        elif val.type == 'uniform':
            job_prior.uniform_min_value = val.min
            job_prior.uniform_max_value = val.max
        job_prior.save()

    job_sampler = Sampler(job=bilby_job, sampler_choice=sampler.sampler_choice)
    job_sampler.save()

    for key, val in sampler.items():
        if key not in ['sampler_choice']:
            sampler_param = SamplerParameter(job=bilby_job, sampler=job_sampler, name=key, value=val)
            sampler_param.save()


    