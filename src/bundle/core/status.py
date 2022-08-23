import os

from core.misc import get_scheduler
import db
from scheduler.scheduler import EScheduler
from scheduler.status import JobStatus
import settings


def get_submit_status(job):
    """
    Gets the status of the job submission step for slurm. If the job submission step is successful, it removes the
    submit_id from the job record and updates it. If the job submission fails for some reason the job is deleted.

    :param job: The internal job db record for the job to get the submit status of
    :return: A single job status object, True/False if the job errored
    """
    sched = get_scheduler()

    if 'submit_id' in job:
        _status, info = sched.status(job['submit_id'], job)

        # If the job is a state less than or equal to running, return it's state
        if _status <= JobStatus.RUNNING:
            result = {
                'what': 'submit',
                'status': _status,
                'info': info
            }

            return result, False

        # If the job is not completed, then some other error has occurred
        if _status != JobStatus.COMPLETED:
            # Delete the job from the database
            db.delete_job(job)

            # Report the error
            result = {
                'what': 'submit',
                'status': _status,
                'info': info
            }

            return result, True

        # The batch submission was successful, remove the submit id from the job
        del job['submit_id']
        db.create_or_update_job(job)

    result = {
        'what': 'submit',
        'status': JobStatus.COMPLETED,
        'info': "Completed"
    }

    return result, False


def condor_status(job):
    """
    Process job status for the condor scheduler

    :param job: The internal job object representing the job to check the status for
    :return: The same return type from submit()
    """
    sched = get_scheduler()
    _status, info = sched.status(job['submit_id'], job)
    result = [{
        'what': 'submit',
        'status': _status,
        'info': info
    }]

    if _status <= JobStatus.RUNNING:
        return {
            'status': result,
            'complete': False
        }
    else:
        # Job is completed, or an error occurred
        db.delete_job(job)

        return {
            'status': result,
            'complete': True
        }


def slurm_status(job):
    """
    Process job status for the slurm scheduler

    :param job: The internal job object representing the job to check the status for
    :return: The same return type from submit()
    """
    # First check if we're waiting for the bash submit script to run
    submit_status, error = get_submit_status(job)
    result_status = [submit_status]

    # If there was an error with the submit step, mark the job as completed and return the error status
    if error:
        return {
            'status': result_status,
            'complete': True
        }

    # Get the path to the slurm id's file
    sid_file = os.path.join(job['working_directory'], job['submit_directory'], 'slurm_ids')

    # Check if the slurm_ids file exists
    if not os.path.exists(sid_file):
        return {
            'status': result_status,
            'complete': False
        }

    with open(sid_file, 'r') as f:
        slurm_ids = [line.strip() for line in f.readlines()]

    # Track the job statuses
    had_error = False
    statuses = []

    # Iterate over each job id and record it's status
    sched = get_scheduler()
    for _sid in slurm_ids:
        what = _sid.split(' ')[0]
        sid = _sid.split(' ')[1]

        jid_status, info = sched.status(sid, job)

        result_status.append({
            'what': what,
            'status': jid_status,
            'info': info
        })

        statuses.append(jid_status)

        # If this job is in an error state, remove the job from the database
        if jid_status is not None and jid_status > JobStatus.RUNNING and jid_status != JobStatus.COMPLETED:
            had_error = True

    # Determine if the job is completed. If every status is completed then the job is completed. If any status was an
    # error, then the job is complete
    completed = statuses.count(JobStatus.COMPLETED) == len(statuses) or had_error

    # Delete the job if it's completed
    if completed:
        db.delete_job(job)

    return {
        'status': result_status,
        'complete': completed
    }


def status(details, *args, **kwargs):
    """
    The entry point of the status function which returns the job status and information for the specified job

    :param details: The job details object from the client
    :return: A special dict with the following format:
    {
        'status': [
            {
                'what': The job step or identifier receiving the state update,
                'status': The JobStatus for this state update,
                'info': Any extra details about the state update as a string
            },
            ...
        ],
        'complete': Boolean representing if the job has finished executing or not
    }
    """
    # Get the job
    job = db.get_job_by_id(details['scheduler_id'])
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

    # Use the relevant scheduler to obtain the job status
    if settings.scheduler == EScheduler.CONDOR:
        return condor_status(job)
    elif settings.scheduler == EScheduler.SLURM:
        return slurm_status(job)
    else:
        return None
