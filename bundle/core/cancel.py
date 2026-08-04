from core.misc import get_scheduler


def cancel(details, job_data):
    """
    Cancel a running job

    :param details: The job details object from the client
    :param job_data: The internal job db record for the job to cancel
    :return: True if the job was cancelled otherwise False
    """
    sched = get_scheduler()

    if "submit_id" in job_data:
        return sched.cancel(job_data["submit_id"], details)

    return False
