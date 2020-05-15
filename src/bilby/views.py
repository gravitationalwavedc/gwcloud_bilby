import datetime
import json

import jwt
from django.conf import settings
from django.db import transaction
import requests

from .forms import BilbyJobForm
from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Prior, Sampler, SamplerParameter


def create_bilby_job(user_id, start, data, signal, prior, sampler):
    # validate_form = BilbyJobForm(data={**start, **data, **signal, **sampler})
    # should be making use of cleaned_data below

    with transaction.atomic():
        bilby_job = BilbyJob(
            user_id=user_id,
            name=start.name,
            description=start.description,
            private=start.private
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

        # Create the jwt token
        jwt_enc = jwt.encode(
            {
                'userId': user_id,
                'exp': datetime.datetime.now() + datetime.timedelta(days=30)
            },
            settings.JOB_CONTROLLER_JWT_SECRET,
            algorithm='HS256'
        )

        # Create the parameter json
        params = bilby_job.as_json()

        print(params)

        # Construct the request parameters to the job controller, note that parameters must be a string, not an objects
        data = {
            "parameters": json.dumps(params),
            "cluster": "ozstar",
            "bundle": "fbc9f7c0815f1a83b0de36f957351c93797b2049"
        }

        # Initiate the request to the job controller
        result = requests.request(
            "POST", settings.GWCLOUD_JOB_CONTROLLER_API_URL + "/job/",
            data=json.dumps(data),
            headers={
                "Authorization": jwt_enc
            }
        )

        # Check that the request was successful
        if result.status_code != 200:
            # Oops
            msg = f"Error submitting job, got error code: {result.status_code}\n\n{result.headers}\n\n{result.content}"
            print(msg)
            raise Exception(msg)

        print(f"Job submitted OK.\n{result.headers}\n\n{result.content}")

        # Parse the response from the job controller
        result = json.loads(result.content)

        # Save the job id
        bilby_job.job_id = result["jobId"]
        bilby_job.save()

        return bilby_job.id
