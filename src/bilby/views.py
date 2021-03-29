from django.db import transaction

# from .forms import BilbyJobForm
from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Prior, Sampler, SamplerParameter, Label
from .utils.jobs.submit_job import submit_job
from .variables import bilby_parameters


def create_bilby_job(user, start, data, signal, prior, sampler):
    # validate_form = BilbyJobForm(data={**start, **data, **signal, **sampler})
    # should be making use of cleaned_data below

    with transaction.atomic():
        bilby_job = BilbyJob(
            user_id=user.user_id,
            name=start.name,
            description=start.description,
            private=start.private,
            is_ligo_job=False
        )
        bilby_job.save()

        job_data = Data(job=bilby_job, data_choice=data.data_choice)
        job_data.save()

        for key, val in data.items():
            if key not in ['data_choice']:
                # Check that non-ligo users only have access to GWOSC channels for real data
                # Note that we're checking for not simulated here, rather than for real, because the backend
                # explicitly checks for `if input_params["data"]["type"] == "simulated":`, so any value other than
                # `simulation` would result in a real data job
                if job_data.data_choice != bilby_parameters.SIMULATED[0] and \
                        key in ['hanford_channel', 'livingston_channel', 'virgo_channel'] and \
                        val != "GWOSC":
                    # This is a real job, with a channel that is not GWOSC
                    if not user.is_ligo:
                        # User is not a ligo user, so they may not submit this job
                        raise Exception("Non-LIGO members may only run real jobs on GWOSC channels")
                    else:
                        # User is a ligo user, so they may submit the job, but we need to track that the job is a
                        # ligo "proprietary" job
                        bilby_job.is_ligo_job = True

                data_param = DataParameter(job=bilby_job, data=job_data, name=key, value=val)
                data_param.save()

        job_signal = Signal(job=bilby_job, signal_choice=signal.signal_choice, signal_model=signal.signal_model)
        job_signal.save()

        for key, val in signal.items():
            if key not in ['signal_choice', 'signal_model'] and val != '':
                signal_param = SignalParameter(job=bilby_job, signal=job_signal, name=key, value=val)
                signal_param.save()

        job_prior = Prior(job=bilby_job, name="prior", prior_choice=prior.prior_choice)
        job_prior.save()
        # for key, val in prior.items():
        #     job_prior = Prior(job=bilby_job, name=key, prior_choice=val.type)
        #     if val.type == 'fixed':
        #         job_prior.fixed_value = val.value
        #     elif val.type == 'uniform':
        #         job_prior.uniform_min_value = val.min
        #         job_prior.uniform_max_value = val.max
        #     job_prior.save()

        job_sampler = Sampler(job=bilby_job, sampler_choice=sampler.sampler_choice)
        job_sampler.save()

        for key, val in sampler.items():
            if key not in ['sampler_choice']:
                sampler_param = SamplerParameter(job=bilby_job, sampler=job_sampler, name=key, value=val)
                sampler_param.save()

        # Submit the job to the job controller

        # Create the parameter json
        params = bilby_job.as_json()

        result = submit_job(user, params)

        # Save the job id
        bilby_job.job_id = result["jobId"]
        bilby_job.save()

        return bilby_job.id


def update_bilby_job(job_id, user, private=None, labels=None):
    bilby_job = BilbyJob.get_by_id(job_id, user)

    if user.user_id == bilby_job.user_id:
        if labels is not None:
            bilby_job.labels.set(Label.filter_by_name(labels))

        if private is not None:
            bilby_job.private = private

        bilby_job.save()

        return 'Job saved!'
    else:
        raise Exception('You must own the job to change the privacy!')
