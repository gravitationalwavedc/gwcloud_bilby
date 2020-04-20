import os

from db import get_job_by_id, update_job, delete_job
from scheduler.slurm import slurm_status, SLURM_STATUS
from scheduler.status import JobStatus


def get_submit_status(job):
    if 'submit_id' in job:
        _status, info = slurm_status(job['submit_id'])

        # If the job is a state less than or equal to running, return it's state
        if _status <= JobStatus.RUNNING:
            result = {
                'what': 'submit',
                'status': _status,
                'info': info
            }

            return result

        # If the job is not completed, then some other error has occured
        if _status != JobStatus.COMPLETED:
            # Delete the job from the database
            delete_job(job)

            # Report the error
            result = {
                'what': 'submit',
                'status': _status,
                'info': info
            }

            return result

        # The batch submission was successful, remove the submit id from the job
        del job['submit_id']
        update_job(job)

    result = {
        'what': 'submit',
        'status': JobStatus.COMPLETED,
        'info': "Completed"
    }

    return result


def status(details, job_data):
    # Get the job
    job = get_job_by_id(details['scheduler_id'])
    if not job:
        # Job doesn't exist. Report error
        result = [{
            'what': "system",
            'status': JobStatus.ERROR,
            'info': "Job does not exist. Perhaps it failed to start?"
        }]

        return {
            'status': result,
            'complete': True
        }

    # First check if we're waiting for the bash submit script to run
    status = [get_submit_status(job)]

    # Get the path to the slurm id's file
    sid_file = os.path.join(job['working_directory'], job['submit_directory'], 'slurm_ids')

    # Check if the slurm_ids file exists
    if not os.path.exists(sid_file):
        return {
            'status': status,
            'complete': False
        }

    with open(sid_file, 'r') as f:
        slurm_ids = [line.strip() for line in f.readlines()]

    # Iterate over each job id and record it's status
    for _sid in slurm_ids:
        what = _sid.split(' ')[0]
        sid = _sid.split(' ')[1]

        _status, info = slurm_status(sid)

        status.append({
            'what': what,
            'status': _status,
            'info': info
        })

        if _status is not None:
            # If this job is in an error state, remove the job from the database
            if _status > JobStatus.RUNNING and _status != JobStatus.COMPLETED:
                delete_job(job)

    return {
        'status': status,
        'complete': True
    }
